# ==============================================================================
# Enterprise MCP Agent Automation Makefile
# ==============================================================================

SHELL := /bin/bash
PYTHON := python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help install lock check-env check-docker test test-unit test-e2e lint clean

help:
	@echo "Available commands:"
	@echo "  make install       Install dependencies from requirements.lock"
	@echo "  make lock          Generate deterministic requirements.lock using pip-tools"
	@echo "  make check-env     Run Phase 0 Hardware & Ollama verification gate"
	@echo "  make check-docker  Run Task 0.3 Docker SDK & sandbox constraint gate"
	@echo "  make test-unit     Run all unit tests (zero external network dependencies)"
	@echo "  make test-e2e      Run full integration tests (requires Ollama & Docker)"
	@echo "  make test          Run all tests"
	@echo "  make lint          Run Ruff linter and Mypy static type checking"
	@echo "  make clean         Remove build artifacts, caches, and test logs"

install:
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.lock

lock:
	$(BIN)/pip install pip-tools>=7.4.0
	$(BIN)/pip-compile --generate-hashes --output-file=requirements.lock pyproject.toml --extra=dev

check-env:
	$(BIN)/python scripts/check_env.py

check-docker:
	$(BIN)/python scripts/test_docker_socket.py

test-unit:
	$(BIN)/pytest -m unit tests/unit/

test-e2e:
	$(BIN)/pytest -m e2e tests/e2e/

test:
	$(BIN)/pytest tests/

lint:
	$(BIN)/ruff check src/ tests/
	$(BIN)/mypy src/

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache build dist *.egg-info htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete