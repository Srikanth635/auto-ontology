// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';
import { authorsRequested, withTagAuthors } from '@/lib/tagAuthors';

// tagsApi.getAll — list tags.
//
// Author names are added only when asked for — see `authorsRequested`. This is
// the hottest tag route there is, read on every navigation the picker survives,
// and the settings page is the only caller with anything to show them in.
export const GET = route(async (req) =>
	authorsRequested(req) ? withTagAuthors(await proxyToBackend(req)) : proxyToBackend(req),
);

// tagsApi.create — add a tag. The identity goes down so the
// backend can record who created it, and comes back resolved to a name
// unconditionally: this answer only ever redraws the row on the settings page,
// which is the page that shows authors.
export const POST = route(async (req, { user }) =>
	withTagAuthors(await proxyToBackend(req, { userId: user.id })),
);
