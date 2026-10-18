# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# ---------------------------------------------------------------------------
# Auto Ontology local helpers
# ---------------------------------------------------------------------------
# Image builds for the local Docker Compose stack, and schema migrations.
#
# Variables (override on the command line):
#
#   TAG             Image tag. Defaults to `git describe`.
#   PYTHON_API_URL  Backend URL baked into the frontend's Next.js rewrites
#                   at build time. Defaults to http://auto-ontology:3001
#                   (the backend service name in docker-compose.yml).
# ---------------------------------------------------------------------------

TAG            ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
PYTHON_API_URL ?= http://auto-ontology:3001

BACKEND_REF  := auto-ontology:$(TAG)
FRONTEND_REF := auto-ontology-frontend:$(TAG)

.PHONY: help build build-backend build-frontend

help:
	@echo "Auto Ontology targets:"
	@echo "  make build               Build both images locally"
	@echo "  make build-backend       Build backend image locally"
	@echo "  make build-frontend      Build frontend image locally"
	@echo ""
	@echo "Schema targets (backend owns the \`auto_ontology\` schema; Prisma owns \`public\`):"
	@echo "  make migrate             Apply Alembic migrations (alembic upgrade head)"
	@echo "  make migrate-check       Fail if the schema has drifted from the metadata"
	@echo "  make migrate-revision m=\"...\"  Autogenerate a revision from auto_ontology/dal/schema.py"

build-backend:
	docker build -t $(BACKEND_REF) .

build-frontend:
	docker build --build-arg PYTHON_API_URL=$(PYTHON_API_URL) \
	    -t $(FRONTEND_REF) ./frontend

build: build-backend build-frontend

# --- Schema migrations -------------------------------------------------
# The backend owns the `auto_ontology` Postgres schema. Prisma owns `public` and migrates
# separately (frontend/prisma/migrate.sh); the two are independent.

migrate:
	uv run alembic upgrade head

# Fails when auto_ontology/dal/schema.py and the database disagree. Run this in CI:
# a schema change committed without its migration is invisible until deploy.
migrate-check:
	uv run alembic check

migrate-revision:
	@test -n "$(m)" || (echo 'usage: make migrate-revision m="what changed"' >&2; exit 2)
	uv run alembic revision --autogenerate -m "$(m)"

.PHONY: migrate migrate-check migrate-revision
