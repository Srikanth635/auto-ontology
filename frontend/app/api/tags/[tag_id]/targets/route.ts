// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';
import { withTagAuthors } from '@/lib/tagAuthors';

// tagsApi.getTargets — one page of the objects a tag labels.
//
// Authors unconditionally, without the `?authors=` the tag list gates them
// behind: the "Tagged By" column is a column of this table rather than an extra
// a caller may not render, so a page of rows with unresolved ids would be a
// page with a blank column.
export const GET = route(async (req) => withTagAuthors(await proxyToBackend(req)));

// tagsApi.attach — label an object with an existing tag.
//
// The identity goes down for the backend's `tagged_by`, which the tag's page
// shows in its "Tagged By" column — the one thing distinguishing a label a
// person applied from one a rule matched.
export const POST = route(async (req, { user }) => proxyToBackend(req, { userId: user.id }));
