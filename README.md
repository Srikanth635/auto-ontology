<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# neemontology

neemontology is a lightweight, single-user fork of
[NVIDIA Auto Ontology](https://github.com/NVIDIA/auto-ontology), set up to run
on your own machine with the model provider of your choice.

Agents can query databases, but a revenue metric answered faster is worth
nothing if the number is wrong. They need a context layer that says where data
lives, what it means, and how to use it. neemontology builds that layer — a
semantic layer of business terms, descriptions and relationships — from a SQL
database's own structure, and uses it to answer natural-language questions with
SQL.

It lets you:

- **Discover:** generate a semantic layer (terms, column descriptions,
  relationships between tables) from your database's metadata.
- **Ground:** give questions trusted business meaning for metrics, entities and
  relationships, and certify the definitions you have checked.
- **Validate:** check generated SQL against the catalog before it runs, and see
  the SQL and the rows behind every answer.
- **Expose:** serve the same context to scripts and agents through the HTTP API.
- **Learn:** fold certified corrections back into the semantic layer, so answers
  improve as you curate it.

> **Input is a SQL database.** neemontology reads tables and columns through its
> connectors (PostgreSQL, MySQL, SQLite, DuckDB, Snowflake, Databricks). It does
> not read documents, import OWL/RDF ontologies, or build a knowledge graph from
> unstructured text. CSV or Parquet files can be loaded into a SQLite or DuckDB
> file first.

## How this branch differs from upstream

| Area | Upstream Auto Ontology | neemontology |
| --- | --- | --- |
| Models | NVIDIA NIM endpoints | Your choice per role under **Settings → Models**: OpenAI, Anthropic, or any OpenAI-compatible server (Ollama, vLLM, …) |
| Access | Sign-in, users, groups, roles, zones and row owners | No sign-in, one local user, ports bound to `127.0.0.1` |
| Agent integration | MCP server, OAuth provider, API tokens, agent skills | The plain HTTP API |
| Background jobs | Ingestion and compilation every 24 hours | Once at startup, then on demand; adding a connection ingests and compiles it straight away |
| Deployment | Helm chart, release tooling, Vault, SSO, invitations | Docker Compose only |
| Connectors | Also HeavyDB, Kyuubi, Trino, ClickHouse | PostgreSQL, MySQL, SQLite, DuckDB, Snowflake, Databricks |
| Look | NVIDIA black and green | Slate and indigo |

Kept as they were: KumoRFM predictive queries, pgAdmin, PII detection, tags and
rules, import/export of the semantic model, and the analytics page.

The app, the Docker images and the container names say neemontology. A few
internal identifiers still use the upstream name — the `auto_ontology` Python
package, the Compose service names, the Postgres database name and the
`x-auto-ontology-user-id` header — so existing data keeps working and the code
stays easy to compare with upstream.

## Benchmarks

To run a text-to-SQL benchmark such as BIRD, refer to the
[ontology SQL evaluation repository](https://github.com/NVIDIA/ontology-sql-eval/).

> **Licensing.** neemontology, like Auto Ontology, is distributed under the
> [Apache License 2.0](./LICENSE). Third-party open-source components
> bundled, linked, or otherwise used by this project are listed in
> [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md).

<p>
<img src="./docs/assets/arch.png" alt="Upstream Auto Ontology architecture" width="800">
</p>

The diagram is upstream's; in this branch the MCP server and sign-in are gone.

## Key Features

- **Natural-language querying** of structured data — questions are translated to
  SQL and executed against connected databases, with the models of your choice:
  OpenAI, Anthropic, or any OpenAI-compatible server such as Ollama or vLLM.
- **Semantic catalog / ontology layer** over relational sources, stored in
  Postgres alongside the catalog it describes.
- **Web UI** for chat, analysis, the data catalog, the glossary of terms, an
  exploration graph, analytics, and settings.
- **Local deployment** — Docker Compose brings up the full stack, for one
  person on their own machine (no sign-in; see [Access](#access)).

## Software Components

| Component           | Technology                                                             | Role                                       | Default port |
| ------------------- | ---------------------------------------------------------------------- | ------------------------------------------ | ------------ |
| Frontend            | Next.js 16 (React 19, TypeScript, Tailwind CSS 4), Prisma              | Web UI, API gateway                        | 3000         |
| Backend             | FastAPI (Python 3.12+), LangChain                                      | Chat / NL-to-SQL, catalog, datasource APIs | 3001         |
| Ingestion worker    | FastAPI (Python 3.12+)                                                 | Ingests tabular data and writes embeddings | 3002         |
| Postgres + pgvector | Relational Database                                                    | App metadata, the catalog and ontology, vector store | 5432 |

### Models

Choose a provider and model for each job under **Settings → Models**:

| Role | Used for | Providers |
| --- | --- | --- |
| Chat | Answering questions, writing SQL, building the semantic layer | OpenAI, Anthropic, NVIDIA NIM, OpenAI-compatible |
| Fast chat | Entity extraction, follow-up questions, charts (defaults to Chat) | OpenAI, Anthropic, NVIDIA NIM, OpenAI-compatible |
| Embeddings | Vector search over the catalog and glossary | OpenAI, NVIDIA NIM, OpenAI-compatible |
| Reranking | Optional; ordering candidates when linking bridge tables | NVIDIA NIM, any Cohere-style `/rerank` API (Cohere, Jina, Voyage, vLLM), or Off |

Until you save something else, every role starts on NVIDIA NIM with the upstream
models (`nvidia/nemotron-3-nano-30b-a3b` for chat and fast chat,
`nvidia/nemotron-3-embed-1b` for embeddings,
`nvidia/llama-nemotron-rerank-vl-1b-v2` for reranking). Only the API key is
missing; enter it on each card (fast chat follows chat), and reranking switches on
with it.

"NVIDIA NIM" uses NVIDIA's hosted API (`https://integrate.api.nvidia.com/v1`, an
`nvapi-` key from build.nvidia.com) or your own NIM when you set a base URL.
Embeddings sent to it carry NVIDIA's `input_type` (`passage` when storing,
`query` when searching), as upstream does. Changing the embedding model
re-embeds everything.

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
  OpenAI-compatible server such as Ollama. You enter it in the UI.
- Connection details for the source database(s) you want to query
  (PostgreSQL, MySQL, SQLite, DuckDB, Snowflake, or Databricks).

### Installation

1. Clone the `neemontology` branch:

   ```bash
   git clone -b neemontology https://github.com/Srikanth635/auto-ontology.git neemontology
   cd neemontology
   ```

2. Create your environment file (.env). The start script in step 3 does this for
   you on first run: it copies the template and generates a random
   `AUTH_SECRET`. To set the Postgres credentials, `CONNECTION_STRINGS` and the
   rest first, create it yourself and edit it. See
   [`.env.example`](./.env.example) for the full list of variables:

   ```bash
   cp .env.example .env
   # edit .env
   ```

   Note:
   - `AUTH_SECRET` is **required**: it encrypts the API keys you save under
     Settings → Models. If it is missing or empty, the start script generates
     one; a value you set is never replaced. Changing it later means entering
     those keys again.
   - `POSTGRES_PORT` only changes the **host-side** port mapping (set it if
     5432 is already taken on your machine); containers always reach Postgres
     on the internal network port.

3. Build the images and start the stack:

   ```bash
   ./dev_tools/setup_env.sh
   ```

   The script creates `.env` if it is missing and fills in `AUTH_SECRET` if it is empty, then runs
   `docker compose up -d --build`. It also stops and starts the stack for you:

   | Command | What it does |
   |---|---|
   | `./dev_tools/setup_env.sh` | Build and start everything |
   | `./dev_tools/setup_env.sh --stop` | Stop everything (your data is kept) |
   | `./dev_tools/setup_env.sh --status` | List the containers and their state |
   | `./dev_tools/setup_env.sh --logs [service]` | Follow the logs, e.g. `--logs ingestion-service` |

   Running `docker compose up -d --build` yourself does the same thing. This builds the backend (`auto-ontology`) and frontend (`auto-ontology-frontend`) images, brings
   up Postgres and pgAdmin, runs the one-shot migration jobs to set up the
   database schema, and starts the app (backend, ingestion service, and
   frontend).

4. Open the UI at <http://localhost:3000> (the backend API is on `:3001`,
   pgAdmin on `:5050`). There is no sign-in — see [Access](#access).

5. Under **Settings → Models**, choose a chat model and an embedding model.
   Then turn on **Settings → Semantic Compilation** and add a connection under
   **Settings → Connections**. The database is ingested and its semantic layer
   built straight away; once that finishes you can ask questions in **Chat**.

   Upgrading an install from before this branch removed sign-in is safe: the
   migrations drop the account, zone and group tables, and existing
   conversations move to the local user.

## Connections Management

neemontology resolves the source databases it connects to from two sources:

1. **Added through the UI** — connections created from within the app. The
   full connection object (including the password) is JSON-serialized and
   stored, **unencrypted**, on the catalog's database row in Postgres.

2. **`CONNECTION_STRINGS` environment variable** — a comma-separated list of
   connection strings supplied at deploy time in `.env`. When it is set it
   takes over: ingestion uses only these, and connections added in the UI are
   ignored. Leave it empty to manage connections in the UI.

**NEEMs: drop them in `data/`.** Every SQLite NEEM in the repo's `data/` folder
(`.sqlite`, `.sqlite3`, `.db`, or a SQLite `.sql` dump) is merged into one
PostgreSQL database, `neem`, which then shows up in the catalog like any other
connection. There is nothing to configure: copy a file into `data/`, or drop it
on the **NEEMs** page in the app, and the ingestion service picks it up within a
few seconds — a changed file is reloaded and a deleted one's rows are removed,
each followed by a catalog refresh and, with semantic compilation on, a
compilation pass. Compilation only covers tables that have no Term yet, so once
the first NEEM is compiled, later NEEMs with the same structure add rows but
nothing to compile.

How the merge keeps NEEMs apart:

- Every table gets a `neem_source_id` column, and `neem_sources` lists the files,
  so a question can be scoped to one NEEM and a file's rows can be removed
  exactly.
- Integer ids (and the foreign keys that point at them) are shifted into a
  range per file: the first NEEM keeps its ids, later ones never collide with
  it, and joins stay single-column.
- A `UNIQUE` key that is not an id holds per NEEM, so two NEEMs can both name
  their robot `pr2`.
- Tables and columns first seen in a later NEEM are added; nothing is dropped.

Subfolders of `data/` are not scanned. `NEEM_DATABASE`, `NEEM_POLL_SECONDS` and
`NEEM_MAX_UPLOAD_MB` (default 500) in `.env` adjust the defaults.

**Other SQLite and DuckDB files.** To connect a file as a database of its own
instead, put it in a subfolder of `data/` (Compose mounts the folder at `/data`)
and list it in `.env`, then restart. While it is set, connections added in the
UI are ignored (the NEEM database is kept either way):

```bash
CONNECTION_STRINGS=sqlite:////data/other/inventory.sqlite
# several: comma-separated, e.g. sqlite:////data/other/a.sqlite,sqlite:////data/other/b.duckdb
```

The name after the last `/` (without the extension) becomes the database name,
so give each file a different name. Files in `data/` are git-ignored.

Each connection is ingested when it is added or changed, and every connection
is ingested again when the ingestion service starts. With semantic compilation
on, a compilation pass follows each ingest. Nothing runs on a timer; use
**Settings → Semantic Compilation** to rebuild the semantic layer on demand.

## Access

neemontology is set up for one person on their own machine: there is **no
sign-in, no user accounts and no roles**. Everyone who can reach the frontend can
do everything, and everything they do is recorded as the single local user.

For that reason Docker Compose publishes the frontend (`:3000`), backend
(`:3001`) and ingestion service (`:3002`) on `127.0.0.1` only. Only change those
port mappings in `docker-compose.yml` on a network you trust, and never expose
the backend or ingestion ports: they accept every request.

Scripts can call the same API the UI uses, with no token:

```sh
curl http://localhost:3000/api/terms
```

```python
import requests

answer = requests.post(
    "http://localhost:3000/api/chat/completions",
    json={"question": "How many orders shipped last week?"},
).text
```

The full surface is described in
[`docs/openapi/auto-ontology-api.json`](./docs/openapi/auto-ontology-api.json).

## Agent API conversations

Clients call the Next.js gateway at `POST /api/chat/completions`. The response is an SSE stream containing `step`,
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

Browser and script callers should use the Next.js gateway, which forwards the
internal `x-auto-ontology-user-id` header to FastAPI. A direct FastAPI request
without `conversation_id` remains stateless; a direct request with
`conversation_id` requires that header.

The web UI manages the UUID automatically. An API-created conversation can be
opened in the UI at `/chat?focus=<conversation_id>`.

## License

neemontology is a fork of NVIDIA Auto Ontology and, like it, is licensed under the [Apache License, Version 2.0](./LICENSE).
SPDX identifier: `Apache-2.0`.

Each source file inherited from Auto Ontology carries NVIDIA's SPDX header
of the form:

```text
SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
All rights reserved.
SPDX-License-Identifier: Apache-2.0
```

Third-party open-source components used by neemontology are enumerated, with their
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

External materials neemontology interacts with at run time:

| Material | When | Terms |
| --- | --- | --- |
| The model providers you configure under Settings → Models (OpenAI, Anthropic, or an OpenAI-compatible endpoint) | Chat, ingestion, and semantic compilation | Terms of that provider and model |
| KumoRFM predictive-query service | Only when `KUMO_RFM_API_KEY` is set | Kumo's terms |
| Your source databases | Ingestion, profiling, and query execution | Your agreements for those systems |

## Contributing

This branch is a personal fork. Changes to upstream Auto Ontology go through
[NVIDIA/auto-ontology](https://github.com/NVIDIA/auto-ontology), which is
currently not accepting external contributions; its security reporting
process is in [`SECURITY.md`](./SECURITY.md). The development workflow for this
repository is in [`CONTRIBUTING.md`](./CONTRIBUTING.md) and
[`CLAUDE.md`](./CLAUDE.md).
