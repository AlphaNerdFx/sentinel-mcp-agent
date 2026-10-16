# ==============================================================================
# Enterprise ReAct MCP Agent - Production Automation Makefile (Whitespace-Safe)
# ==============================================================================

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Invariant: Prioritize local relative path to guarantee ZERO spaces in executable path
ifneq ($(wildcard .venv/bin/python*),)
	PYTHON := .venv/bin/python3
else ifneq ($(wildcard venv/bin/python*),)
	PYTHON := venv/bin/python3
else
	PYTHON := python3
endif

# Execute tooling strictly through Python module interface (-m)
RUFF := $(PYTHON) -m ruff
MYPY := $(PYTHON) -m mypy
PYTEST := $(PYTHON) -m pytest
PIP := $(PYTHON) -m pip
PIP_SYNC := $(PYTHON) -m piptools sync

.PHONY: help install lock check-docker lint lint-fix test-unit test-e2e test ci clean

help:
	@echo "Available Automation Targets:"
	@echo "  make ci        Execute complete end-to-end CI pipeline"
	@echo "  make lint      Run static analysis and format validation"
	@echo "  make test      Run unit and e2e integration suites"

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
