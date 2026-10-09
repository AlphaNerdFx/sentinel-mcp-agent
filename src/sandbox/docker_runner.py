import docker
import time
from dataclasses import dataclass

class DockerDaemonUnavailableError(Exception):
    pass

@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool

class DockerPythonSandbox:
    def __init__(
        self,
        image: str = "python:3.11-slim",
        memory_limit: str = "256m",
        cpu_quota: float = 1.0,
        timeout_seconds: int = 5,
    ) -> None:
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota
        self.timeout_seconds = timeout_seconds
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as exc:
            raise DockerDaemonUnavailableError(f"Docker daemon is unreachable: {exc}")

    def execute_code(self, script_contents: str) -> ExecutionResult:
        start_time = time.perf_counter()
        container = None
        timed_out = False
        
        # Enforce execution safety constraints
        nano_cpus = int(self.cpu_quota * 1_000_000_000)
        cmd = ["python", "-u", "-c", script_contents]

        try:
            container = self.client.containers.create(
                image=self.image,
                command=cmd,
                network_mode="none",
                mem_limit=self.memory_limit,
                memswap_limit=self.memory_limit,
                nano_cpus=nano_cpus,
                read_only=True,
                tmpfs={"/tmp": "rw,size=16m"},
                user="nobody",  # Drop root permissions
                detach=True
            )
            
            container.start()
            
            # Poll status until timeout expiration
            poll_interval = 0.1
            elapsed = 0.0
            finished = False
            
            while elapsed < self.timeout_seconds:
                container.reload()
                if container.status in ["exited", "dead"]:
                    finished = True
                    break
                time.sleep(poll_interval)
                elapsed += poll_interval
            
            if not finished:
                timed_out = True
                try:
                    container.kill()
                except Exception:
                    pass
                exit_code = 124  # Standard POSIX timeout code
            else:
                result = container.wait()
                exit_code = result.get("StatusCode", 1)

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            
        except Exception as err:
            return ExecutionResult(
                stdout="",
                stderr=f"Runtime container failure: {str(err)}",
                exit_code=1,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                timed_out=False
            )
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        duration_ms = (time.perf_counter() - start_time) * 1000
        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out
        )