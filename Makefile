# ==============================================================================
# Enterprise ReAct MCP Agent - Production Automation Makefile
# Target Standard: Forward Deployed Engineering Baseline (LTS 2026)
# ==============================================================================

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Dynamic Virtualenv & Binary Binding
ifeq ($(wildcard .venv/bin/python),)
    PYTHON ?= python3
    PYTEST ?= pytest
    PIP ?= pip
    PIP_SYNC ?= pip-sync
    RUFF ?= ruff
    MYPY ?= mypy
else
    VENV := .venv
    PYTHON ?= $(VENV)/bin/python
    PYTEST ?= $(VENV)/bin/pytest
    PIP ?= $(VENV)/bin/pip
    PIP_SYNC ?= $(VENV)/bin/pip-sync
    RUFF ?= $(VENV)/bin/ruff
    MYPY ?= $(VENV)/bin/mypy
endif

.PHONY: help install lock check-env check-docker lint lint-fix test-unit test-e2e test ci clean purge-legacy-tests

help:
	@echo "Available Automation Targets:"
	@echo "  make install              Synchronize dependencies from requirements.lock via pip-sync"
	@echo "  make lock                 Compile deterministic requirements.lock using pip-tools"
	@echo "  make check-docker         Validate Docker socket connectivity and permissions"
	@echo "  make lint                 Run Ruff linter and format validation"
	@echo "  make lint-fix             Automatically resolve fixable lint and import formatting"
	@echo "  make test-unit            Run all hermetic unit test suites"
	@echo "  make test-e2e             Run user story integration tests (US-01..US-03)"
	@echo "  make ci                   Execute complete end-to-end CI validation pipeline"
	@echo "  make clean                Purge build caches, WAL files, and bytecode"

install:
	$(PIP) install --upgrade pip pip-tools
	$(PIP_SYNC) requirements.lock

lock:
	$(PIP) install --upgrade pip-tools
	pip-compile --generate-hashes --output-file=requirements.lock pyproject.toml --extra=dev

check-docker:
	@echo "==> Verifying Docker daemon and sandbox image availability..."
	@docker info > /dev/null 2>&1 || (echo "ERROR: Docker daemon is not running." && exit 1)
	@docker image inspect python:3.11-slim > /dev/null 2>&1 || (echo "Pulling python:3.11-slim..." && docker pull python:3.11-slim)
	@echo "[Certain] Docker environment verified."

lint:
	@echo "==> Running static style, typing, and import audits..."
	$(RUFF) check src/ tests/
	$(RUFF) format --check src/ tests/
	$(MYPY) src/
	@echo "[Certain] Static linting passed with zero errors."

lint-fix:
	@echo "==> Automatically resolving formatting and import ordering..."
	$(RUFF) check --fix src/ tests/
	$(RUFF) format src/ tests/

test-unit:
	@echo "==> Executing hermetic unit test suites..."
	$(PYTEST) tests/unit/ -v --durations=10

test-e2e:
	@echo "==> Executing End-to-End User Story verification..."
	$(PYTEST) tests/e2e/ -v --durations=10

test: test-unit test-e2e

ci: check-docker lint test-unit
	@echo "==> Validating FastMCP Stdio Stream Segregation (ADR-0013)..."
	@STDOUT_PAYLOAD=$$( $(PYTHON) src/server.py < /dev/null ); \
	if [ -n "$$STDOUT_PAYLOAD" ]; then \
		echo "CRITICAL: ADR-0013 Stream Segregation Violation! Detected raw bytes on stdout:"; \
		echo "$$STDOUT_PAYLOAD"; \
		exit 1; \
	fi
	@echo "[Certain] FastMCP stdout stream purity confirmed."
	@echo "==> Running Full Test Suite..."
	$(PYTEST) tests/ -v
	@echo "======================================================================"
	@echo " [Certain] ALL CI GATES PASSED: SYSTEM MEETS PRD V1.2.0 SPECIFICATIONS"
	@echo "======================================================================"

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache build dist *.egg-info htmlcov .coverage
	rm -f .agent_state.db* .test_phase2_state.db* test_guardrails_metrics.db*
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete