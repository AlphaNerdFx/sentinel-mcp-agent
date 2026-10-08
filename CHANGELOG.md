
# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-08

### Added

- Phase 0 hardware and environment validation script (`scripts/check_env.py`) with NVML and CLI fallbacks.
- Python Docker SDK socket and cgroup constraint verification gate (`scripts/test_docker_socket.py`).
- PEP 621 compliant `pyproject.toml` and cryptographically locked `requirements.lock`.
- POSIX automation `Makefile` for environment checking, dependency locking, and test runs.
- Production `.gitignore` excluding SQLite databases, credentials, and build caches.
- Architectural Decision Records: ADR-10 (Ollama Multi-Model Residency), ADR-11 (MCP Stdio Client Bridge), and ADR-12 (Resilient GPU Telemetry).

### Fixed

- Addressed Ollama cold-start read timeout by implementing an explicit pre-warm stage with `keep_alive: -1`.
- Migrated deprecated `pynvml` dependency to `nvidia-ml-py`.
