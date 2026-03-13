.PHONY: help up down logs shell test lint install

PYTHON ?= python3
DC = docker compose

help:
	@echo "pretix-email-restrictions development targets"
	@echo ""
	@echo "  make up       Start the full pretix stack (pretix + postgres + redis)"
	@echo "  make down     Stop and remove containers"
	@echo "  make logs     Follow container logs"
	@echo "  make shell    Open a bash shell inside the pretix container"
	@echo "  make test     Run the automated test suite (pytest)"
	@echo "  make lint     Run ruff linter"
	@echo "  make install  Install the plugin locally in editable mode (for local dev)"

up:
	$(DC) up -d
	@echo ""
	@echo "pretix is starting at http://localhost:8345"
	@echo "Run 'make logs' to follow startup, then 'make demo' to seed test data."

demo:
	@echo "Waiting for pretix to be ready..."
	$(DC) exec pretix bash -c "until pretix migrate --run-syncdb 2>/dev/null; do sleep 3; done"
	$(DC) exec pretix pretix setup_demo

down:
	$(DC) down

logs:
	$(DC) logs -f pretix

shell:
	$(DC) exec pretix bash

# ---------------------------------------------------------------------------
# Tests (run locally, not inside Docker)
# ---------------------------------------------------------------------------
test:
	DATA_DIR=/tmp/pretix-test PRETIX_INSTANCE_NAME=CI SITE_URL=http://localhost \
	$(PYTHON) -m pytest tests/ -v

test-cov:
	DATA_DIR=/tmp/pretix-test PRETIX_INSTANCE_NAME=CI SITE_URL=http://localhost \
	$(PYTHON) -m pytest tests/ -v --cov=pretix_email_restrictions --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check pretix_email_restrictions/ tests/

install:
	pip install -e .
