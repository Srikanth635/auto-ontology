// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Forward a request to the Python (FastAPI) backend, preserving method, path,
// query, and body. The frontend and backend share the same `/api/...` path, so
// we forward the incoming pathname verbatim.

import { buildInternalIdentityHeaders } from '@/lib/internalIdentity';

const PYTHON_API_URL = process.env.PYTHON_API_URL ?? 'http://127.0.0.1:3001';

/**
 * What every proxied answer is allowed to be kept in, which is nothing shared.
 *
 * Next does not cache Route Handlers, so this is about the browser: a GET that
 * states no policy is left to heuristic freshness, and an edit would then not
 * show up until the stale copy expired.
 *
 * Exported because a wrapper that rebuilds one of these responses has to carry
 * it through rather than decide it again — see `withTagAuthors`.
 */
export const PROXY_CACHE_CONTROL = 'private, no-store';

/**
 * `userId` names the caller to the backend, for routes that record who did
 * something (a tag's `created_by`, for instance). Opt-in rather than always
 * forwarded, so a route that has no use for an identity does not imply one.
 *
 * It comes from `route()`'s local user, and the header set is rebuilt from
 * scratch below — so a client cannot smuggle in an identity of its own
 * choosing by sending the header itself.
 *
 * `streamBody` pipes the request body through untouched, for binary uploads.
 */
export async function proxyToBackend(
	req: Request,
	{ userId, streamBody = false }: { userId?: string; streamBody?: boolean } = {},
): Promise<Response> {
	const incoming = new URL(req.url);
	const target = `${PYTHON_API_URL}${incoming.pathname}${incoming.search}`;

	const headers: Record<string, string> = { Accept: 'application/json' };
	const contentType = req.headers.get('content-type');
	if (contentType) headers['Content-Type'] = contentType;
	if (userId) Object.assign(headers, buildInternalIdentityHeaders(userId));

	const hasBody = req.method !== 'GET' && req.method !== 'HEAD';
	let init: RequestInit;
	if (hasBody && streamBody) {
		// Piped through rather than read: an upload can be hundreds of
		// megabytes, and `text()` would both buffer all of it and mangle every
		// byte that is not valid UTF-8. `duplex` is required by fetch for a
		// streamed request body and is missing from the DOM typings.
		const contentLength = req.headers.get('content-length');
		if (contentLength) headers['Content-Length'] = contentLength;
		init = { method: req.method, headers, body: req.body, duplex: 'half' } as RequestInit;
	} else {
		init = { method: req.method, headers, body: hasBody ? await req.text() : undefined };
	}

	const upstream = await fetch(target, init);

	// Relayed as bytes: decoding as text would replace every byte of a binary
	// answer, such as the Ossie export's zip, that is not valid UTF-8.
	const respBody = await upstream.arrayBuffer();
	return new Response(respBody, {
		status: upstream.status,
		headers: {
			'Content-Type': upstream.headers.get('content-type') ?? 'application/json',
			'Cache-Control': PROXY_CACHE_CONTROL,
		},
	});
}
