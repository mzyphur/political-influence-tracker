.PHONY: install test lint lock fetch-core discover-core roster aec-annual-summary aec-money pdf-text senate-interests classify-entities pipeline pipeline-smoke db-up db-load api-dev

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/ruff check .

# Regenerate requirements.lock from pyproject.toml. Run this whenever direct
# dependencies change in pyproject.toml. Requires pip-tools (a dev dependency
# declared in pyproject.toml [project.optional-dependencies].dev). Lockfile
# diffs should be treated as intentional reproducibility changes; do not
# hand-edit requirements.lock.
lock:
	.venv/bin/python -m piptools compile pyproject.toml --extra dev -o requirements.lock

fetch-core:
	.venv/bin/python -m au_politics_money.cli fetch-source aec_transparency_downloads
	.venv/bin/python -m au_politics_money.cli fetch-source aph_contacts_csv
	.venv/bin/python -m au_politics_money.cli fetch-source aph_members_interests_48
	.venv/bin/python -m au_politics_money.cli fetch-source aph_senators_interests
	.venv/bin/python -m au_politics_money.cli fetch-source aec_federal_boundaries_gis

discover-core:
	.venv/bin/python -m au_politics_money.cli discover-links aec_transparency_downloads
	.venv/bin/python -m au_politics_money.cli discover-links aph_contacts_csv
	.venv/bin/python -m au_politics_money.cli discover-links aph_members_interests_48
	.venv/bin/python -m au_politics_money.cli discover-links aph_senators_interests
	.venv/bin/python -m au_politics_money.cli discover-links aec_federal_boundaries_gis

roster:
	.venv/bin/python -m au_politics_money.cli build-roster

aec-annual-summary:
	.venv/bin/python -m au_politics_money.cli summarize-aec-annual

aec-money:
	.venv/bin/python -m au_politics_money.cli normalize-aec-annual-money-flows

pdf-text:
	.venv/bin/python -m au_politics_money.cli extract-pdf-text
	.venv/bin/python -m au_politics_money.cli extract-house-interest-sections
	.venv/bin/python -m au_politics_money.cli extract-house-interest-records

senate-interests:
	.venv/bin/python -m au_politics_money.cli fetch-senate-interests-api
	.venv/bin/python -m au_politics_money.cli extract-senate-interest-records

classify-entities:
	.venv/bin/python -m au_politics_money.cli classify-entities

pipeline:
	.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline

pipeline-smoke:
	.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline --smoke

db-up:
	docker compose up -d

db-load:
	.venv/bin/python -m au_politics_money.cli load-postgres --apply-schema

api-dev:
	.venv/bin/dotenv -f .env run -- .venv/bin/uvicorn au_politics_money.api.app:app --reload --host 127.0.0.1 --port 8008
