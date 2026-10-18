<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Auto Ontology in a broader stack

Honest map of what this repository implements versus what a partner wires.
Do not invent a first-party blueprint that is not here.

## Auth contract

Auto Ontology authenticates browsers with a Better Auth cookie. Services and
scripts use an Auto Ontology API token; MCP clients use an OAuth access token
Auto Ontology issued at sign-in. There is no SSO or external-IdP bearer path.

Credential order on every `/api` route (`frontend/auth/resolve-user.ts`):

1. Session cookie
2. Auto Ontology API token (`auto_ontology_…`, `x-api-key` or Bearer)
3. OAuth bearer issued by Auto Ontology (MCP)

A revoked API token is a 401; it is not retried as another credential.

## Models (deployment config)

Chat, embeddings and reranking use whichever providers an admin chose under
Settings → Models: OpenAI, Anthropic, or any OpenAI-compatible server. That is
configuration, not a model training or fine-tuning integration.

Roles: chat (NL-to-SQL), fast chat (entity extraction; defaults to chat),
embeddings, and optional reranking. A role with nothing saved falls back to
`REASONING_*` / `NON_REASONING_*` / `EMBED_*` / `RERANK_*` env vars, then
`DEFAULT_MODELS_*`.

Ingest and query share one embedding setting. Changing it re-embeds every
vector in the background (`GET /api/model-settings/reembed` reports progress).

## cuOpt (partner-wired)

This repository has **no** cuOpt client, skill, or job bridge. Auto Ontology returns
natural-language answers, the SQL it ran, and rows. A partner agent may take
those numbers and call cuOpt. Use NVIDIA's `cuopt-*` skills for formulation
and solve. Do not claim Auto Ontology schedules routes or solves LPs itself.

## Calling rules that bite in a stack

- Partners call the Next.js gateway (`APP_URL` / `:3000`), never public
  FastAPI `:3001`.
- MCP holds no deployment-wide identity. Each caller signs in as themselves.
- `conversation_id` is per Auto Ontology user. Do not share UUIDs across users.
- Overlapping turns on one conversation: `409`.
