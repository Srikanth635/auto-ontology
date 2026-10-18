// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Names the user ids a tag read carries, for the Tags settings pages: a tag's
 * own `created_by` / `modified_by`, and the `tagged_by` on each object a tag
 * labels.
 *
 * There is no sign-in, so the only person who can author anything is the one
 * local user, shown as "You". Any other id — a rule, an import, or nothing —
 * reads as "Auto Generated", exactly as a null does.
 */

import { PROXY_CACHE_CONTROL } from '@/lib/server/proxy-backend';
import { LOCAL_USER_ID } from '@/lib/server/route';
import { AUTHORS_PARAM, AUTHORS_PARAM_ON } from '@/constants/tags';

/**
 * Whether this read should carry authors. The param is what keeps the work off
 * the tag picker's path, which reads the same list on every detail page and
 * throws authors away.
 */
export const authorsRequested = (req: Request): boolean =>
	new URL(req.url).searchParams.get(AUTHORS_PARAM) === AUTHORS_PARAM_ON;

const LOCAL_AUTHOR = { id: LOCAL_USER_ID, name: 'You', email: '' } as const;

type Row = Record<string, unknown>;

const isRow = (value: unknown): value is Row => typeof value === 'object' && value !== null;

/**
 * The rows in a `{ data }` envelope — one from a write, a list from a read.
 *
 * Tags on the tag routes, and the objects a tag labels on its `targets` route.
 * The two are read the same way here because they are enriched the same way:
 * whichever author columns a row carries get resolved, and a row carrying none
 * costs nothing.
 */
const rowsIn = (payload: Row): Row[] => {
	const rows = Array.isArray(payload.data) ? payload.data : [payload.data];
	return rows.filter(isRow);
};

/** The local user when *value* names it, otherwise null ("Auto Generated"). */
const authorOf = (value: unknown) => (value === LOCAL_USER_ID ? LOCAL_AUTHOR : null);

/**
 * The upstream answer, rebuilt around a body this module may have rewritten.
 *
 * The cache policy is *carried* rather than decided again. This wrapper sits on
 * top of `proxyToBackend`, which is where a proxied answer's policy is set, and
 * rebuilding a response is exactly where such a header goes missing — the enriched
 * branch of `/api/tags` would then be the one reply on that route with no policy
 * at all, while carrying the most caller-specific body of the two.
 */
const respond = (body: string, upstream: Response): Response =>
	new Response(body, {
		status: upstream.status,
		headers: {
			'Content-Type': upstream.headers.get('content-type') ?? 'application/json',
			'Cache-Control': upstream.headers.get('cache-control') ?? PROXY_CACHE_CONTROL,
		},
	});

/**
 * The backend's answer with `created_by_user` / `modified_by_user` — and, on a
 * page of tagged objects, `tagged_by_user` — added beside the ids it stored.
 *
 * Every branch that cannot add them answers with the body unchanged rather than
 * failing: an error response or a body that is not the expected envelope.
 */
export const withTagAuthors = async (upstream: Response): Promise<Response> => {
	const body = await upstream.text();
	if (!upstream.ok) return respond(body, upstream);

	let payload: unknown;
	try {
		payload = JSON.parse(body);
	} catch {
		return respond(body, upstream);
	}
	if (typeof payload !== 'object' || payload === null) return respond(body, upstream);

	// Mutated in place, so the envelope keeps whatever else it carries — a
	// list's `count`, a page's `total`. Set only where the row has the column,
	// so a tag does not gain a `tagged_by_user` it has no id for.
	for (const row of rowsIn(payload as Row)) {
		if ('created_by' in row || 'modified_by' in row) {
			row.created_by_user = authorOf(row.created_by);
			row.modified_by_user = authorOf(row.modified_by);
		}
		if ('tagged_by' in row) {
			row.tagged_by_user = authorOf(row.tagged_by);
		}
	}

	return respond(JSON.stringify(payload), upstream);
};
