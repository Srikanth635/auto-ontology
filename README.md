<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Auto Ontology

Agents can retrieve documents and query databases, but reliability gates agentic analytics: a revenue metric answered faster is worth nothing if the number is wrong. Agents need a context layer that tells them where data lives, what it means, whether to use it, how to use it, where it came from, and what is similar. NVIDIA Auto Ontology is an open library that builds that layer from enterprise metadata, reconciles definitions across systems, and exposes it to any agent harness through MCP, CLI, and API. It complements the semantic models customers already own.

It enables developers to:

- Discover: generate enterprise ontologies from metadata; connect existing ontologies and semantic models; build AI-ready knowledge graphs.
- Ground: give agents trusted business meaning for metrics, entities, and relationships; reconcile inconsistent definitions across systems.
- Validate: check generated queries against certified definitions and lineage; return provenance with every answer.
- Expose: serve context to any agent harness through MCP, CLI, and API.
Learn: fold certified corrections and usage back into the ontology, so shared context improves with every question.

## Benchmarks

To run a text-to-SQL benchmark such as BIRD, refer to the
[ontology SQL evaluation repository](https://github.com/NVIDIA/ontology-sql-eval/).

> **Licensing & contributions.** Auto Ontology is distributed under the
> [Apache License 2.0](./LICENSE). Third-party open-source components
> bundled, linked, or otherwise used by this project are listed in
> [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md). **This project
> is currently not accepting external contributions.**

<p>
<img src="./docs/assets/arch.png" alt="Auto Ontology Architecture" width="800">
</p>

## Key Features

- **Natural-language querying** of structured data — questions are translated to
  SQL and executed against connected databases, with the models of your choice:
  OpenAI, Anthropic, or any OpenAI-compatible server such as Ollama or vLLM.
- **Semantic catalog / ontology layer** over relational sources, stored in
  Postgres alongside the catalog it describes.
- **Authentication & RBAC** —using [Better Auth](https://github.com/better-auth/better-auth).
- **Web UI** for chat, analysis, data catalog, analytics, and settings.
- **Local deployment** — Docker Compose brings up the full stack.

## Software Components

| Component           | Technology                                                             | Role                                       | Default port |
| ------------------- | ---------------------------------------------------------------------- | ------------------------------------------ | ------------ |
| Frontend            | Next.js 16 (React 19, TypeScript, Tailwind CSS 4), Better Auth, Prisma | Web UI, authentication, API gateway        | 3000         |
| Backend             | FastAPI (Python 3.12+), LangChain                                      | Chat / NL-to-SQL, catalog, datasource APIs | 3001         |
| Ingestion worker    | FastAPI (Python 3.12+)                                                 | Ingests tabular data and writes embeddings | 3002         |
| Postgres + pgvector | Relational Database                                                    | App metadata, the catalog and ontology, vector store | 5432 |

### Models

Choose a provider and model for each job under **Settings → Models**:

| Role | Used for | Providers |
| --- | --- | --- |
| Chat | Answering questions, writing SQL, building the semantic layer | OpenAI, Anthropic, OpenAI-compatible |
| Fast chat | Entity extraction, follow-up questions, charts (defaults to Chat) | OpenAI, Anthropic, OpenAI-compatible |
| Embeddings | Vector search over the catalog and glossary | OpenAI, OpenAI-compatible |
| Reranking | Optional; ordering candidates when linking bridge tables | Off, or any Cohere-style `/rerank` API (Cohere, Jina, Voyage, vLLM) |

"OpenAI-compatible" covers any server that speaks the OpenAI API: Ollama,
vLLM, LM Studio, OpenRouter, Azure OpenAI and others. Each card has **Test**
(one small real call) and **Load models** (lists the provider's model ids).

- **Keys are stored encrypted** in Postgres with a key derived from
  `AUTH_SECRET`, and are never sent back to the browser. Changing `AUTH_SECRET`
  makes stored keys unreadable, so they have to be entered again.
- **Changes apply without a restart**, from the next request.
- **Changing the embedding model re-embeds everything** in the background, since
  vectors from two models can't be compared. Nothing curated is lost: the
  vectors are rebuilt from the stored catalog and glossary. Vectors are stored
  at 2048 dimensions; a model that emits more (for example
  `text-embedding-3-large`) needs **Dimensions** set to 2048 or fewer.

Anthropic has no embeddings API, so pair a Claude chat model with OpenAI or a
local embedding model.

For headless setups, a role with nothing saved in the UI falls back to
environment variables (`REASONING_*`, `NON_REASONING_*`, `EMBED_*`, `RERANK_*`,
each falling back to `DEFAULT_MODELS_*`). See [`.env.example`](./.env.example).

## Deployment

### Prerequisites

- **Docker** with **Docker Compose v2** (e.g. Docker Desktop on macOS/Windows,
  Docker Engine on Linux) for the local stack.
- An API key for a model provider (OpenAI, Anthropic), or a local
  OpenAI-compatible server such as Ollama. You enter it in the UI after sign-in.
- Connection details for the source database(s) you want to query
  (Databricks, Postgres, Snowflake, or DuckDB).

### Installation

1. Clone the repository:

   ```bash
   git clone <repo-url> auto_ontology && cd auto_ontology
   ```

2. Create your environment file (.env) from the template and fill in the values
   (Postgres credentials, `AUTH_SECRET`, the admin account, `CONNECTION_STRINGS`, etc.).
   See [`.env.example`](./.env.example) for the full list of variables:

   ```bash
   cp .env.example .env
   # edit .env
   ```

   Note:
   - `AUTH_SECRET` and `APP_URL` are **required** — without them every page
     fails with a Better Auth "default secret" error.
   - `POSTGRES_PORT` only changes the **host-side** port mapping (set it if
     5432 is already taken on your machine); containers always reach Postgres
     on the internal network port.

3. Build the images and start the stack:

   ```bash
   docker compose up -d --build
   ```

   This builds the backend (`auto_ontology`) and frontend (`auto-ontology-frontend`) images, brings
   up Postgres and pgAdmin, runs the one-shot `frontend-migrate` job to
   sync the database schema, and starts the app (backend, ingestion service,
   and frontend).

4. Open the UI at <http://localhost:3000> (the backend API is on `:3001`,
   pgAdmin on `:5050`).

   > **Troubleshooting:** if the UI loads without the left navigation panel
   > (or otherwise looks broken after a restart), your browser is holding a
   > stale session cookie — this happens when `AUTH_SECRET` changes or the
   > database is reset. Clear the site data for `localhost:3000` (or delete
   > the `better-auth.session_token` cookie) and sign in again.

## Connections Management

Auto Ontology resolves the source databases it connects to from two sources:

1. **Added through the UI** — connections created from within the app. The
   full connection object (including the password) is JSON-serialized and
   stored, **unencrypted**, on the catalog's database row in Postgres.

2. **`CONNECTION_STRINGS` environment variable** — a comma-separated list of
   connection strings supplied at deploy time in `.env`. This is a fallback: it
   is used only when there are no UI-added connections.

## Authentication

Auto Ontology signs users in with email and password. Self-service sign-up is
disabled: the only account is the bootstrap admin from
`AUTO_ONTOLOGY_ADMIN_EMAIL` / `AUTO_ONTOLOGY_ADMIN_PASSWORD` in `.env`, which is
created (or has its password reset) every time the frontend starts.

### API tokens (scripting)

A browser signs in and gets a session cookie, which a script cannot obtain. For
scripts, notebooks, and scheduled jobs, mint an **API token** instead:

1. Open the user menu (top right) → **API Tokens** → **New token**.
2. Name it, optionally pick an expiry (default: never), and **copy the token**.
   Auto Ontology stores only a SHA-256 hash of it, so it is shown exactly once. Losing it
   means minting a new one.

Send it as `x-api-key` on any `/api/...` call — `Authorization: Bearer <token>`
works too:

```sh
curl -H "x-api-key: $AUTO_ONTOLOGY_API_TOKEN" https://auto_ontology.example.com/api/terms
```

```python
import os
import requests

session = requests.Session()
session.headers["x-api-key"] = os.environ["AUTO_ONTOLOGY_API_TOKEN"]

terms = session.get("https://auto_ontology.example.com/api/terms").json()

answer = session.post(
    "https://auto_ontology.example.com/api/chat/completions",
    json={"question": "How many orders shipped last week?"},
).json()
```

Things worth knowing:

- **A token acts as its owner.** It carries no permissions of its own — every
  call is authorized against the owner's role, exactly as it would be in the
  browser. A viewer's token cannot do admin things.
- **The whole API surface accepts it.** Authentication is resolved in one place
  (`frontend/auth/resolve-user.ts`) for every route, so any endpoint in
  [`docs/openapi/auto-ontology-api.json`](./docs/openapi/auto-ontology-api.json) that is not
  `withPublic` works with a token.
- **Revocation is immediate.** Delete the token in the UI, or delete/ban the
  owning user, and the next request with it gets a 401.
- **Tokens cannot manage tokens.** Creating and revoking requires a signed-in
  session, so a leaked token cannot issue itself successors.
  
## Agent API conversations

Public clients call the authenticated Next.js gateway at
`POST /api/chat/completions`. The response is an SSE stream containing `step`,
`result`, or `error` events, followed by `[DONE]`.

`conversation_id` is optional:

- Omit it for a stateless, one-shot request.
- Supply a client-generated UUID to create or continue a conversation.
- Reuse the same UUID for every turn in the thread. Wait for `[DONE]` before
  sending the next turn; overlapping requests for one conversation return
  `409 Conversation in progress`.

```json
{
  "question": "What about last month?",
  "conversation_id": "d61d8aa3-d496-4fa7-97ce-4f831c162e7f"
}
```

For conversational requests, FastAPI loads up to the five most recent completed
turns (bounded to 12,000 characters) and rewrites contextual input such as
“What about August?” into a standalone question before running the existing
text-to-SQL graph. Independent questions are passed through unchanged. Internal
agent thoughts, chart payloads, errors, and raw SQL result sets are not reused as
context.

Conversation history is scoped to the authenticated Auto Ontology user. Browser and
service callers should use the Next.js gateway, which resolves the user and
forwards the internal `x-auto-ontology-user-id` header to FastAPI. The FastAPI port is a
trusted internal service boundary: it must not be exposed publicly because that
header is not independently verified by FastAPI. A direct FastAPI request
without `conversation_id` remains stateless; a direct request with
`conversation_id` requires the trusted identity header.

The web UI manages the UUID automatically. An API-created conversation can be
opened in the UI at `/chat?focus=<conversation_id>` when it belongs to the
signed-in user.

## Agent skills

Coding agents: start at [`AGENTS.md`](./AGENTS.md). Skills live in
[`skills/`](./skills/) (`nvidia-ontology-setup`, `nvidia-ontology-management`, `nvidia-ontology-query`).
Maintainers keep using [`CLAUDE.md`](./CLAUDE.md).

## MCP server

Agent harnesses such as Cursor and Claude Desktop can query your data through
Auto Ontology's [MCP](https://modelcontextprotocol.io) server. See
[`mcp/`](./mcp/) to run it and [`docs/mcp.md`](./docs/mcp.md) for the details.

## License

Auto Ontology is licensed under the [Apache License, Version 2.0](./LICENSE).
SPDX identifier: `Apache-2.0`.

Each NVIDIA-authored source file in this repository carries an SPDX header
of the form:

```text
SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
All rights reserved.
SPDX-License-Identifier: Apache-2.0
```

Third-party open-source components used by Auto Ontology are enumerated, with their
upstream licenses and project URLs, in
[`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md). Components added by the
container images are listed separately in
[`CONTAINER_THIRD_PARTY_NOTICES.md`](./CONTAINER_THIRD_PARTY_NOTICES.md).

## Notice and Disclaimer

NOTICE AND DISCLAIMER: This software automatically retrieves, accesses or
interacts with external materials. Those retrieved materials are not
distributed with this software and are governed solely by separate terms,
conditions and licenses. You are solely responsible for finding, reviewing and
complying with all applicable terms, conditions, and licenses, and for
verifying the security, integrity and suitability of any retrieved materials
for your specific use case. This software is provided "AS IS", without warranty
of any kind. The author makes no representations or warranties regarding any
retrieved materials, and assumes no liability for any losses, damages,
liabilities or legal consequences from your use or inability to use this
software or any retrieved materials. Use this software and the retrieved
materials at your own risk.

External materials Auto Ontology interacts with at run time:

| Material | When | Terms |
| --- | --- | --- |
| The model providers you configure under Settings → Models (OpenAI, Anthropic, or an OpenAI-compatible endpoint) | Chat, ingestion, and semantic compilation | Terms of that provider and model |
| KumoRFM predictive-query service | Only when `KUMO_RFM_API_KEY` is set | Kumo's terms |
| Your source databases | Ingestion, profiling, and query execution | Your agreements for those systems |

## Contributing

**This project is currently not accepting contributions.** Issues, pull
requests, and patches submitted from outside the Auto Ontology maintainer team will
not be reviewed or merged. Security-relevant reports should follow the
process described in [`SECURITY.md`](./SECURITY.md). Maintainer workflow is in
[`CONTRIBUTING.md`](./CONTRIBUTING.md).
