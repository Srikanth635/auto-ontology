// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Resolve the Auto Ontology user behind a request, for handlers that accept both browser
// and service callers.
//
// Three credentials are accepted, in order:
//   1. A Better Auth session cookie (browser).
//   2. A Auto Ontology API token, `x-api-key: auto_ontology_...` (scripts, CI — see auth/api-token.ts).
//      Checked before the OAuth bearer because both may arrive as `Authorization:
//      Bearer`, and only the API-token path recognises the `auto_ontology_` prefix.
//   3. A Auto Ontology-issued OAuth access token (an MCP client whose user signed in
//      through Auto Ontology — see auth/oauth-token.ts). Opaque like an API token, so it
//      is checked after that path has claimed the `auto_ontology_` prefix.

import { headers } from 'next/headers';
import { getCurrentSession } from '@/auth/auth-guards';
import { extractApiToken, verifyApiToken } from '@/auth/api-token';
import { extractOAuthToken, verifyOAuthToken } from '@/auth/oauth-token';

export type ResolvedUser = { id: string; role: string | null };

/**
 * Resolve the Auto Ontology user behind the current request — from the session cookie, a
 * Auto Ontology API token, or a Auto Ontology-issued OAuth access token. Returns null when
 * the caller is unauthenticated. This is the single entry point browser, script,
 * and MCP callers all go through, so every protected API accepts any of the
 * three credentials.
 */
export async function resolveUser(): Promise<ResolvedUser | null> {
	const session = await getCurrentSession();
	if (session?.user.id) return { id: session.user.id, role: session.user.role ?? null };

	const requestHeaders = await headers();

	if (extractApiToken(requestHeaders)) return verifyApiToken(requestHeaders);
	if (extractOAuthToken(requestHeaders)) return verifyOAuthToken(requestHeaders);

	return null;
}

/**
 * Convenience wrapper returning just the resolved user id (or null). See
 * {@link resolveUser}.
 */
export async function resolveUserId(): Promise<string | null> {
	return (await resolveUser())?.id ?? null;
}
