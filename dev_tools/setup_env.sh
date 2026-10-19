#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Commands that act on a running stack. They don't need .env checks or a build.
case "${1:-}" in
--stop)
	# `down` without -v: the postgres_data volume (catalog, semantic layer,
	# settings) survives, so the next start picks up where this one left off.
	docker compose down
	exit 0
	;;
--status)
	docker compose ps -a
	exit 0
	;;
--logs)
	shift
	docker compose logs -f --tail=200 "$@"
	exit 0
	;;
esac

# Every service reads .env (env_file in docker-compose.yml). First run: create it
# from the template, with a freshly generated AUTH_SECRET instead of the
# placeholder, so there is nothing to fill in by hand to get started.
generate_secret() {
	if command -v openssl >/dev/null 2>&1; then
		openssl rand -hex 32
	else
		head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
	fi
}

set_auth_secret() {
	local secret tmp
	secret="$(generate_secret)"
	tmp="$(mktemp)"
	grep -Ev '^AUTH_SECRET=' .env >"$tmp" || true
	echo "AUTH_SECRET=$secret" >>"$tmp"
	cat "$tmp" >.env
	rm -f "$tmp"
}

if [[ ! -f .env ]]; then
	cp .env.example .env
	set_auth_secret
	echo "Created .env from .env.example with a generated AUTH_SECRET."
	echo "Review it (Postgres password, CONNECTION_STRINGS) if you need to."
elif ! grep -Eq '^AUTH_SECRET=.+' .env; then
	# Missing or empty only. A value you already set is never replaced: it
	# encrypts the API keys saved in the app, and changing it loses them.
	set_auth_secret
	echo "AUTH_SECRET was empty in .env; generated one."
fi

INFRA_SERVICES="postgres pgadmin ingestion-service"
AUTO_ONTOLOGY_SERVICES="auto-ontology auto-ontology-frontend"

resolve_infra_services() {
	local services=""
	for svc in $INFRA_SERVICES; do
		services="$services $svc"
	done
	echo "${services# }"
}

# Tear down any previously-running Auto Ontology app containers so the chosen mode
# starts from a clean slate (infra containers are left alone).
echo "Stopping existing Auto Ontology containers (if any): $AUTO_ONTOLOGY_SERVICES"
docker compose rm -sf $AUTO_ONTOLOGY_SERVICES >/dev/null 2>&1 || true

if [[ " $* " =~ \ --dev\  ]]; then
	SERVICES=$(resolve_infra_services)
	echo "Starting infrastructure: $SERVICES"
	docker compose up -d --build $SERVICES

	echo ""
	echo "Services:"
	echo "  Postgres:      http://localhost:5432"
	echo "  pgAdmin:       http://localhost:5050"
	echo "  Auto Ontology ingestion: http://localhost:3002"

	echo ""
	echo "Start Auto Ontology locally:"
	echo "  uv run python -m auto_ontology.server"
	exit 0
fi

if [[ " $* " =~ \ --ds\  ]]; then
	SERVICES=$(resolve_infra_services)
	# Frontend container reaches the host-side backend via host.docker.internal.
	# Override PYTHON_API_URL for both the build arg (baked into Next.js
	# rewrites) and the runtime env.
	export PYTHON_API_URL="http://host.docker.internal:3001"
	echo "Starting infrastructure + auto-ontology-frontend: $SERVICES auto-ontology-frontend"
	echo "(backend will run locally on the host)"
	# --no-deps skips the auto_ontology dependency declared on auto-ontology-frontend.
	docker compose up -d --build --no-deps $SERVICES auto-ontology-frontend

	echo ""
	echo "Services:"
	echo "  Postgres:      http://localhost:5432"
	echo "  pgAdmin:       http://localhost:5050"
	echo "  Auto Ontology frontend:  http://localhost:3000"
	echo "  Auto Ontology ingestion: http://localhost:3002"

	echo ""
	echo "Start the backend locally:"
	echo "  uv sync"
	echo "  uv run python -m auto_ontology.server"
	echo "  (or use the \"Debug API\" config in .vscode/launch.json)"
	exit 0
fi

# Default: full docker stack (infra + auto_ontology + auto-ontology-frontend)
SERVICES="$(resolve_infra_services) $AUTO_ONTOLOGY_SERVICES"
echo "Starting full stack: $SERVICES"
docker compose up -d --build $SERVICES

echo ""
echo "Services:"
echo "  Postgres:      http://localhost:5432"
echo "  pgAdmin:       http://localhost:5050"
echo "  Auto Ontology frontend:  http://localhost:3000"
echo "  Auto Ontology backend:   http://localhost:3001"
echo "  Auto Ontology ingestion: http://localhost:3002"

echo ""
echo "Follow the logs:  ./dev_tools/setup_env.sh --logs [service]"
echo "Stop everything:  ./dev_tools/setup_env.sh --stop"
