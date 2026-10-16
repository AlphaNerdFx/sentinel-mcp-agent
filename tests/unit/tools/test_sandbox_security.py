"""
tests/unit/tools/test_sandbox_security.py
Validates Docker container execution constraints, timeouts, memory caps,
and network isolation with image pre-flight verification.
Contract Reference: SPEC_V1.md COMP-05; PRD_V1.md ADR-03, US-03.
"""

import time

import docker
import pytest

from src.sandbox.docker_runner import DockerPythonSandbox, ExecutionResult

try:
    _client = docker.from_env()
    _client.ping()
    DOCKER_AVAILABLE = True
except Exception:
    DOCKER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not DOCKER_AVAILABLE, reason="Docker daemon socket (/var/run/docker.sock) unreachable."
)


@pytest.fixture(scope="module")
def sandbox():
    """
    [Certain] Pre-flights local Docker image cache and instantiates sandbox.
    Guarantees python:3.11-slim is present before test execution begins.
    """
    client = docker.from_env()
    image_tag = "python:3.11-slim"
    try:
        client.images.get(image_tag)
    except docker.errors.ImageNotFound:
        client.images.pull(image_tag)

    return DockerPythonSandbox(
        image=image_tag,
        memory_limit="256m",
        cpu_quota=1.0,
        timeout_seconds=5,
    )


class TestDockerSandboxSecurity:
    def test_standard_computation_execution(self, sandbox):
        """[Certain] Verifies benign Python computation completes with zero exit code."""
        code = "print(sum([x * 2 for x in range(10)]))"
        result: ExecutionResult = sandbox.execute_code(code)

        assert result.exit_code == 0
        assert result.stdout.strip() == "90"
        assert not result.timed_out
        assert result.duration_ms > 0

    def test_network_isolation_enforcement(self, sandbox):
        """
        [Certain] Verifies network isolation (--network none).
        Attempts to open outbound TCP connections must fail with Linux Errno 101.
        """
        code = """
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.0)
    s.connect(("8.8.8.8", 53))
    print("BREACH: Socket connected!")
except OSError as e:
    print(f"BLOCKED: {e.errno}")
"""
        result: ExecutionResult = sandbox.execute_code(code)

        assert result.exit_code == 0
        assert "BLOCKED: 101" in result.stdout
        assert "BREACH" not in result.stdout

    def test_hard_timeout_enforcement(self, sandbox):
        """
        [Certain] Verifies infinite loops/sleeps are terminated by the host
        watchdog at the 5.0-second boundary.
        """
        code = """
import time
time.sleep(30)
print("BREACH: Slept past deadline!")
"""
        start_time = time.perf_counter()
        result: ExecutionResult = sandbox.execute_code(code)
        elapsed_seconds = time.perf_counter() - start_time

        assert result.timed_out is True
        assert 4.8 <= elapsed_seconds <= 7.5
        assert "BREACH" not in result.stdout

    def test_memory_limit_oom_termination(self, sandbox):
        """
        [Certain] Verifies allocations exceeding 256m trigger kernel OOM killer
        (Linux Exit Code 137).
        """
        code = """
# Allocate ~400MB in memory (hard limit is 256m)
data = bytearray(400 * 1024 * 1024)
print("BREACH: Allocated 400MB!")
"""
        result: ExecutionResult = sandbox.execute_code(code)

        assert result.exit_code == 137
        assert "BREACH" not in result.stdout

    def test_root_filesystem_read_only_protection(self, sandbox):
        """
        [Certain] Verifies root filesystem is read-only (--read-only).
        Writing to system directories must be intercepted by the OS kernel.
        Accepts either EROFS (Errno 30) or EACCES (Errno 13) depending on VFS checks.
        """
        code = """
try:
    with open('/root/exploit.txt', 'w') as f:
        f.write('malicious payload')
    print("BREACH: Wrote to root filesystem!")
except OSError as e:
    print(f"BLOCKED: {e.errno}")
"""
        result: ExecutionResult = sandbox.execute_code(code)

        assert result.exit_code == 0
        # Kernel VFS returns either 30 (EROFS) or 13 (EACCES) before write commits
        assert any(f"BLOCKED: {code_val}" in result.stdout for code_val in (30, 13))
        assert "BREACH" not in result.stdout

    def test_tmpfs_scratchpad_isolation_and_ephemerality(self, sandbox):
        """
        [Certain] Verifies /tmp is writable as tmpfs, but files do not persist
        across distinct container instances.
        """
        code_write = """
with open('/tmp/test_session.txt', 'w') as f:
    f.write('transient_data')
print('WRITE_SUCCESS')
"""
        result_write = sandbox.execute_code(code_write)
        assert result_write.exit_code == 0
        assert "WRITE_SUCCESS" in result_write.stdout

        code_read = """
import os
if os.path.exists('/tmp/test_session.txt'):
    print('LEAK: File persisted!')
else:
    print('ISOLATED')
"""
        result_read = sandbox.execute_code(code_read)
        assert result_read.exit_code == 0
        assert "ISOLATED" in result_read.stdout
        assert "LEAK" not in result_read.stdout
