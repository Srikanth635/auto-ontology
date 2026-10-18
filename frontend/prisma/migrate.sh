#!/bin/sh
# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Guarded Prisma schema sync for the `frontend-migrate` Compose service.
#
# Runs from /app/migrate, where the image ships the Prisma CLI plus
# prisma.config.ts (datasource url) and prisma/schema.prisma.
#
# Why the guard: `prisma db push` stops rather than drop a table that still
# holds rows, so tables of removed features are dropped explicitly first. Every
# step is idempotent and touches only the `frontend` schema -- the one schema
# Prisma's datasource lists.
set -eu

# Both subcommands read the schema path and datasource url from
# prisma.config.ts (shipped alongside this script in /app/migrate). Prisma 7's
# `db execute` has no --schema flag; it takes the datasource from the config.
PRISMA="node node_modules/prisma/build/index.js"

# `db push` does not create the schema it targets, so this has to exist first
# or the very first push fails with "schema \"frontend\" does not exist".
echo "migrate: ensuring the frontend schema exists..."
$PRISMA db execute --stdin <<'SQL'
CREATE SCHEMA IF NOT EXISTS frontend;
SQL

echo "migrate: dropping tables of removed features (sign-in, API tokens, OAuth, SSO, invitations)..."
# `db push` refuses to drop a table that still has rows, so the tables of
# removed features go explicitly. Dropping "user" with CASCADE also drops the
# foreign keys conversations and analytics had to it, after which their rows
# move to the single local user.
$PRISMA db execute --stdin <<'SQL'
DROP TABLE IF EXISTS frontend.invitations;
DROP TABLE IF EXISTS frontend."ssoProvider";
DROP TABLE IF EXISTS frontend."oauthClientAssertion" CASCADE;
DROP TABLE IF EXISTS frontend."oauthConsent" CASCADE;
DROP TABLE IF EXISTS frontend."oauthAccessToken" CASCADE;
DROP TABLE IF EXISTS frontend."oauthRefreshToken" CASCADE;
DROP TABLE IF EXISTS frontend."oauthClientResource" CASCADE;
DROP TABLE IF EXISTS frontend."oauthResource" CASCADE;
DROP TABLE IF EXISTS frontend."oauthClient" CASCADE;
DROP TABLE IF EXISTS frontend.apikey CASCADE;
DROP TABLE IF EXISTS frontend.verification CASCADE;
DROP TABLE IF EXISTS frontend.account CASCADE;
DROP TABLE IF EXISTS frontend.session CASCADE;
DROP TABLE IF EXISTS frontend."user" CASCADE;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'frontend' AND table_name = 'conversations'
  ) THEN
    UPDATE frontend.conversations SET user_id = 'local' WHERE user_id <> 'local';
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'frontend' AND table_name = 'conversation_analytics'
      AND column_name = 'user_id'
  ) THEN
    UPDATE frontend.conversation_analytics SET user_id = 'local' WHERE user_id <> 'local';
  END IF;
END $$;
SQL

echo "migrate: running prisma db push..."
exec $PRISMA db push
