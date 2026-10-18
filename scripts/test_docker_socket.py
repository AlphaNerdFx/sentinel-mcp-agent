#!/usr/bin/env python3
"""
scripts/test_docker_socket.py
Task 0.3 & COMP-05 Verification: Python Docker SDK Socket & Constraint Gate.
"""

import os
import stat
import sys

import docker
from docker.errors import DockerException

CLR_RESET = "\033[0m"
CLR_GREEN = "\033[92m"
CLR_RED = "\033[91m"
CLR_BLUE = "\033[94m"


def log_pass(msg: str) -> None:
    print(f"  {CLR_GREEN}✔ PASS:{CLR_RESET} {msg}")


def log_fail(msg: str) -> None:
    print(f"  {CLR_RED}✖ FAIL:{CLR_RESET} {msg}")


def verify_docker_runtime() -> bool:
    print(f"{CLR_BLUE}=== [TASK 0.3] Docker Python SDK & Socket Security Gate ==={CLR_RESET}")

    # Step 1: Check UNIX Domain Socket Permissions (Linux/WSL2)
    socket_path = "/var/run/docker.sock"
    if os.path.exists(socket_path):
        mode = os.stat(socket_path).st_mode
        is_socket = stat.S_ISSOCK(mode)
        readable = os.access(socket_path, os.R_OK)
        writable = os.access(socket_path, os.W_OK)

        if is_socket and readable and writable:
            log_pass(f"UNIX domain socket '{socket_path}' is accessible without sudo (R/W OK).")
        else:
            log_fail(f"UNIX socket '{socket_path}' has invalid permissions. Readable={readable}, Writable={writable}.")
            print("    Fix: sudo usermod -aG docker $USER && newgrp docker")
            return False
    else:
        # On Windows native, Docker uses named pipe npipe:////./pipe/docker_engine
        print(f"  ℹ Notice: '{socket_path}' not found. Checking Docker named pipe...")

    # Step 2: Initialize Docker Client from Environment
    try:
        client = docker.from_env()
        ping_ok = client.ping()
        if ping_ok:
            log_pass("Docker Python SDK connected to daemon successfully.")
    except DockerException as e:
        log_fail(f"Failed to connect to Docker daemon via Python SDK: {e}")
        return False

    # Step 3: Test Container Execution under COMP-05 Invariants
    print("  Testing container creation with strict security boundaries...")
    try:
        container = client.containers.run(
            image="python:3.11-slim",
            command="python -c \"import sys; sys.stdout.write('SDK_SOCKET_OK')\"",
            network_mode="none",
            mem_limit="256m",
            memswap_limit="256m",
            nano_cpus=1_000_000_000,
            read_only=True,
            tmpfs={"/tmp": "rw,size=16m"},
            remove=True,
            detach=False,
            stdout=True,
            stderr=True,
        )

        output = container.decode("utf-8").strip()
        if output == "SDK_SOCKET_OK":
            log_pass("COMP-05 container execution verified (network=none, 256MB cap, tmpfs active).")
        else:
            log_fail(f"Container output mismatch: Expected 'SDK_SOCKET_OK', got '{output}'")
            return False

    except Exception as e:
        log_fail(f"Failed to run isolated container via SDK: {e}")
        return False

    # Step 4: Verify Kernel OOM-Killer Kills Memory-Exhaustion Bombs (Exit Code 137)
    print("  Testing deterministic OOM containment (256MB cap)...")
    try:
        # Intentionally allocate 300MB to trigger kernel SIGKILL
        client.containers.run(
            image="python:3.11-slim",
            command="python -c \"x = bytearray(300 * 1024 * 1024)\"",
            mem_limit="256m",
            memswap_limit="256m",
            remove=True,
            detach=False,
        )
        log_fail("Memory limit failed! Container was allowed to allocate > 256MB without being killed.")
        return False
    except docker.errors.ContainerError as e:
        # Exit code 137 = 128 + 9 (SIGKILL from Linux OOM-Killer)
        if e.exit_status == 137:
            log_pass("Deterministic OOM-killer verified: Process killed with exit code 137.")
        else:
            log_fail(f"Container exited with unexpected code: {e.exit_status} (expected 137).")
            return False
    except Exception as e:
        log_fail(f"Unexpected error testing OOM containment: {e}")
        return False

    print(f"\n{CLR_GREEN}>>> Docker verification complete: Task 0.3 fully satisfied.{CLR_RESET}\n")
    return True


if __name__ == "__main__":
    success = verify_docker_runtime()
    sys.exit(0 if success else 1)
