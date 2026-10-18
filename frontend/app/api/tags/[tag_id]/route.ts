// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';
import { authorsRequested, withTagAuthors } from '@/lib/tagAuthors';

// tagsApi.getById — one tag. What it labels is `targets/route.ts` beside this.
//
// Authors on request, by the same rule as the list: this is where the detail
// view reads who curated the tag.
export const GET = route(async (req) =>
	authorsRequested(req) ? withTagAuthors(await proxyToBackend(req)) : proxyToBackend(req),
);

// tagsApi.update — rename a tag. The identity goes down for the backend's `modified_by`, and the renamed tag
// comes back with both authors resolved.
export const PATCH = route(async (req, { user }) =>
	withTagAuthors(await proxyToBackend(req, { userId: user.id })),
);

// tagsApi.delete — remove a tag. Nothing survives the delete to
// record an author on, so no identity is forwarded.
export const DELETE = route((req) => proxyToBackend(req));
