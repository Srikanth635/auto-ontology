<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Auto Ontology setup troubleshooting

Read this before searching the web. Redact secrets before sharing command
output.

## UI loads without the left navigation (or looks broken after restart)

Stale Better Auth session cookie. Happens when `AUTH_SECRET` changes or the
database is reset. Clear site data for `localhost:3000` (or delete the
`better-auth.session_token` cookie) and sign in again.

Every page failing with a Better Auth "default secret" error means `.env` is
missing `AUTH_SECRET` or `APP_URL`. Both are required.

## `POSTGRES_PORT` did not change anything inside the app

`POSTGRES_PORT` only remaps the **host-side** port (`localhost:<port> →
container 5432`). Containers always reach Postgres on 5432 on the compose
network. Set it only when host 5432 is already taken.

## NIM / chat / ingest fail, or embeddings look empty

Chat and ingest need an NVIDIA NIM key. Set `DEFAULT_MODELS_API_KEY` (legacy
fallback: `NVIDIA_API_KEY`). Each model role is a triplet —
`<PREFIX>_ENDPOINT`, `<PREFIX>_API_KEY`, `<PREFIX>_MODEL` — and any unset
field falls back to `DEFAULT_MODELS_*`.

`EMBED_ENDPOINT` and `EMBED_MODEL` **must match** between ingest and query.
A mismatch puts stored vectors and query vectors in different spaces; answers
look like "nothing found."

Confirm the triplets in `.env` are the same for the
ingestion service and the backend.

## Connections: UI vs `CONNECTION_STRINGS`

Auto Ontology resolves source databases from two places:

1. Connections added in the UI. Credentials are stored in plaintext on the
   catalog row.
2. `CONNECTION_STRINGS` (comma-separated) in `.env`. This is a **fallback**: used only when there
   are no UI-added connections.

## MCP client cannot discover how to sign in

`$AUTO_ONTOLOGY_API_URL/.well-known/oauth-authorization-server` must return JSON
(`200`). A redirect to the login page means the deployment predates that
route — run the frontend from the checkout (`pnpm dev`).

`AUTO_ONTOLOGY_API_URL` is the **web app**, default `http://localhost:3000`, not
FastAPI `:3001`.

## Sign-in or MCP login fails although discovery works

Users, sessions, API keys, and the MCP OAuth tables live in the Prisma
`frontend` schema, synced by the `frontend-migrate` job, not by the backend's
`auto-ontology-migrate`. Read its log even if it exited 0; it has finished
without an error before while leaving MCP login broken:

`docker compose logs frontend-migrate`.

## "Protected resource ... does not match expected ..."

The MCP server advertised the address it bound to, and the client reached it
under a different spelling of the same host — almost always `127.0.0.1`
versus `localhost`. Set `AUTO_ONTOLOGY_MCP_PUBLIC_URL` to the URL the client uses, or
leave `AUTO_ONTOLOGY_MCP_HOST` unset.

## "This request carried no signed-in session"

The grant expired or was revoked in Auto Ontology. Sign in again from the MCP client.
There is no server-side token to paste; do not try to configure one.

## `ask_question` returned an empty answer, with no SQL and no error

Call `check_readiness` first. Most often no database connection is
configured. A non-empty `databases` list is not proof SQL can run: the
catalog outlives the connection it was ingested from. Viewing connections is
admin-only by default; a viewer 403 is reported as `unverified`, not a bad
credential.

If the deployment is ready, the question's vocabulary is the problem —
`search_terms` for the nouns in it.

## "Auto Ontology cannot answer right now"

Usually the semantic layer was never compiled; confirm with
`check_readiness` or `GET /api/semantic-compilation/status`. It also appears
when a `conversation_id` already has a turn in flight (`409`).

## Client shows no MCP tools

Check the client's MCP logs. The server logs to stderr. Confirm the client
URL includes the `/mcp` suffix and was restarted after the config change.
