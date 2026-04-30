# Top-level Makefile for the Australian Political Influence Transparency
# project. The targets here are deliberately the *public reproducibility
# entry points* — they wrap the per-component scripts and Make targets so
# any reader can reproduce the data, tests, and frontend artifacts from a
# clean clone with one command per stage.
#
# All commands assume:
#   * Python 3.11+ on PATH.
#   * Node 20+ and npm on PATH.
#   * Docker Desktop running (used by the Postgres container).
#   * `cd` is at the project root.
#
# Inspect any target with `make -n <target>` to see the actual commands it
# will run before executing them. Every command here is also documented in
# `docs/reproducibility.md` and `frontend/public/methodology.html`.

PROJECT_ROOT := $(shell pwd)
BACKEND := $(PROJECT_ROOT)/backend
FRONTEND := $(PROJECT_ROOT)/frontend
DATA := $(PROJECT_ROOT)/data
DOCKER_COMPOSE := /opt/homebrew/bin/docker-compose

# --- Public top-level targets ---------------------------------------------

.PHONY: help bootstrap reproduce-federal reproduce-federal-smoke verify \
        api-dev frontend-dev test test-backend test-frontend lint \
        db-up db-down db-ready db-load \
        fetch-aec-register fetch-postcode-crosswalk \
        load-aec-register load-postcode-crosswalk \
        clean-data clean-state-of-the-world

help:
	@echo "AU Politics — public reproducibility targets:"
	@echo ""
	@echo "  make bootstrap            Install backend venv + frontend npm deps."
	@echo "  make db-up                Start the local Postgres/PostGIS container."
	@echo "  make db-ready             Block until Postgres is ready."
	@echo "  make reproduce-federal    Full federal pipeline against live AEC/APH"
	@echo "                            sources, then load Postgres + verify."
	@echo "  make reproduce-federal-smoke"
	@echo "                            Same chain in --smoke mode for CI/dev."
	@echo "  make verify               Run the post-load verification suite"
	@echo "                            (qa-serving-database + pytest + ruff +"
	@echo "                            frontend build)."
	@echo "  make api-dev              Start the local FastAPI server on :8008."
	@echo "  make frontend-dev         Start the Vite dev server on :5173."
	@echo ""
	@echo "Targeted reproducibility entry points:"
	@echo "  make fetch-aec-register   Fetch the AEC Register of Entities live."
	@echo "  make load-aec-register    Load the latest fetched AEC Register JSONL."
	@echo "  make fetch-postcode-crosswalk"
	@echo "                            Fetch postcodes from the AEC electorate"
	@echo "                            finder using the seed list."
	@echo "  make load-postcode-crosswalk"
	@echo "                            Load the latest postcode crosswalk JSONL."
	@echo ""
	@echo "Maintenance:"
	@echo "  make test                 Run backend + frontend tests."
	@echo "  make lint                 Run backend ruff."
	@echo "  make clean-data           Remove data/raw + data/processed + data/audit."
	@echo "                            Use only when intentionally rebuilding from"
	@echo "                            sources (the script asks for confirmation)."

# --- Bootstrap -------------------------------------------------------------

bootstrap:
	@echo "==> Bootstrapping backend venv"
	cd $(BACKEND) && python3 -m venv .venv
	cd $(BACKEND) && .venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
	@echo "==> Bootstrapping frontend node_modules"
	cd $(FRONTEND) && npm install
	@echo "==> Bootstrap complete"

# --- Database --------------------------------------------------------------

db-up:
	cd $(BACKEND) && $(DOCKER_COMPOSE) -f docker-compose.yml up -d

db-down:
	cd $(BACKEND) && $(DOCKER_COMPOSE) -f docker-compose.yml down

db-ready:
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		if cd $(BACKEND) && $(DOCKER_COMPOSE) -f docker-compose.yml exec -T postgres pg_isready -U au_politics -d au_politics 2>/dev/null; then \
			echo "Postgres is ready"; break; \
		fi; \
		sleep 2; \
	done

db-load:
	cd $(BACKEND) && .venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-postgres --apply-schema

# --- Reproduce federal end-to-end -----------------------------------------

reproduce-federal:
	bash $(PROJECT_ROOT)/scripts/reproduce_federal_from_scratch.sh

reproduce-federal-smoke:
	bash $(PROJECT_ROOT)/scripts/reproduce_federal_from_scratch.sh --smoke

# --- Targeted reproducibility ---------------------------------------------

fetch-aec-register:
	cd $(BACKEND) && .venv/bin/dotenv -f .env run -- \
		.venv/bin/au-politics-money fetch-aec-register-of-entities

load-aec-register:
	cd $(BACKEND) && .venv/bin/dotenv -f .env run -- \
		.venv/bin/au-politics-money load-aec-register-of-entities

fetch-postcode-crosswalk:
	cd $(BACKEND) && .venv/bin/dotenv -f .env run -- \
		.venv/bin/au-politics-money fetch-aec-electorate-finder-postcodes \
		--postcodes-file $(DATA)/seeds/aec_postcode_search_seed.txt --refetch
	cd $(BACKEND) && .venv/bin/dotenv -f .env run -- \
		.venv/bin/au-politics-money normalize-aec-electorate-finder-postcodes \
		--postcodes-file $(DATA)/seeds/aec_postcode_search_seed.txt

load-postcode-crosswalk:
	cd $(BACKEND) && .venv/bin/dotenv -f .env run -- \
		.venv/bin/au-politics-money load-postcode-electorate-crosswalk

# --- Verification ----------------------------------------------------------

verify: test-backend lint
	cd $(BACKEND) && .venv/bin/dotenv -f .env run -- \
		.venv/bin/au-politics-money qa-serving-database
	cd $(FRONTEND) && npm run build

test: test-backend test-frontend

test-backend:
	cd $(PROJECT_ROOT) && \
		AUPOL_RUN_POSTGRES_INTEGRATION=1 \
		DATABASE_URL_TEST=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \
		$(BACKEND)/.venv/bin/pytest $(BACKEND)/tests/ -q

test-frontend:
	cd $(FRONTEND) && npm run build

lint:
	cd $(BACKEND) && .venv/bin/ruff check .

# --- Local dev servers ----------------------------------------------------

api-dev:
	cd $(BACKEND) && $(MAKE) api-dev

frontend-dev:
	cd $(FRONTEND) && npm run dev

# --- Cleanup ---------------------------------------------------------------

clean-data:
	@bash $(PROJECT_ROOT)/scripts/clean_local_data.sh

clean-state-of-the-world:
	@echo "Refusing to do that automatically — see scripts/clean_local_data.sh"
	@echo "and the 'Database Rebuild' section in docs/reproducibility.md."
	@exit 1
