SHELL := /bin/bash
PY := .venv/bin
SAY ?= Bonjour

.PHONY: help install lint test run serve up down logs journal history services service status say doctor token develop egress cdp vnc chrome-reset clean

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

history:  ## report the agent Chrome history (warmup growth)
	$(PY)/mnemosyne history --top $(or $(TOP),15)

services:  ## list per-service journals
	$(PY)/mnemosyne journal --services

service:  ## show one service journal: make service SERVICE=acme
	$(PY)/mnemosyne journal --service "$(SERVICE)"

status:  ## catalog + governor status
	$(PY)/mnemosyne status

say:  ## send a message to the agent: make say SAY="priorise Lacq"
	$(PY)/mnemosyne say "$(SAY)"

doctor:  ## diagnose config, vault, LLM auth, Chrome
	$(PY)/mnemosyne doctor

token:  ## store the GitHub token in the vault (run ALONE, then paste when prompted)
	@if [ -n "$(filter-out token,$(MAKECMDGOALS))" ]; then \
		echo "ATTENTION : n'ajoute rien apres 'make token' (le token finirait dans l'historique)."; \
		echo "Lance 'make token' SEUL, puis colle le token quand c'est demande."; \
		exit 2; \
	fi
	@read -s -p "GitHub token (fine-grained): " T; echo; $(PY)/mnemosyne vault set github_token "$$T"; unset T

develop:  ## self-extension: make develop TASK="Add the Europeana connector"
	$(PY)/mnemosyne develop "$(TASK)"

egress:  ## verify the agent's traffic does not transit Tailscale
	./scripts/check-egress.sh

cdp:  ## check the Chrome DevTools endpoint (shared namespace)
	docker run --rm --network container:mnemosyne-chrome-1 curlimages/curl:latest \
		-s http://127.0.0.1:9222/json/version

vnc:  ## print how to open the noVNC page (local desktop or SSH tunnel)
	@echo "=== CAS 1 : tu as un bureau/écran sur CETTE machine ($(shell hostname)) ==="
	@echo "  Ouvre un navigateur ICI et va sur :"
	@echo "  http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale"
	@echo ""
	@echo "=== CAS 2 : tu es sur TON portable et tu te connectes en SSH ==="
	@echo "  Depuis TON portable, lance :"
	@echo "  ssh -L 6080:127.0.0.1:6080 -L 8080:127.0.0.1:8080 $$(id -un)@$$(tailscale ip -4 2>/dev/null | head -1)"
	@echo "  puis ouvre http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale"
	@echo "  (garde la session SSH ouverte pendant que tu utilises la page)"

chrome-reset:  ## wipe the Chrome profile (removes Google login) and restart it
	docker compose rm -sf chrome
	rm -rf data/chrome-profile
	docker compose up -d chrome
	@echo "fresh profile — reconnect Chrome to Google via make vnc"

clean:  ## remove caches
	rm -rf .pytest_cache .ruff_cache
