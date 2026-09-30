SHELL := /bin/bash
PY := .venv/bin
SAY ?= Bonjour

.PHONY: help install lint test run serve up down logs journal status say doctor egress clean

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

install:  ## create venv and install (dev)
	python3 -m venv .venv
	$(PY)/pip install -e '.[dev]'

lint:  ## ruff
	$(PY)/ruff check .

test:  ## pytest
	$(PY)/pytest -q

run:  ## run the heartbeat locally (foreground)
	$(PY)/mnemosyne run

serve:  ## run the aggregation API locally
	$(PY)/mnemosyne serve

up:  ## docker compose up -d (heartbeat + chrome)
	docker compose up -d --build

down:  ## stop containers
	docker compose down

logs:  ## follow container logs
	docker compose logs -f mnemosyne

journal:  ## print today's journal
	$(PY)/mnemosyne journal

status:  ## catalog + governor status
	$(PY)/mnemosyne status

say:  ## send a message to the agent: make say SAY="priorise Lacq"
	$(PY)/mnemosyne say "$(SAY)"

doctor:  ## diagnose config, vault, LLM auth, Chrome
	$(PY)/mnemosyne doctor

egress:  ## verify the agent's traffic does not transit Tailscale
	./scripts/check-egress.sh

clean:  ## remove caches
	rm -rf .pytest_cache .ruff_cache
