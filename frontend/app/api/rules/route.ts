// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';
import { withTagAuthors } from '@/lib/tagAuthors';

// rulesApi.getAll — list rules.
//
// `withTagAuthors` despite the name: it names `created_by` / `modified_by` in a
// `{ data }` envelope, and a rule stores those two columns as a tag does.
export const GET = route(async (req) => withTagAuthors(await proxyToBackend(req)));

// rulesApi.create — save a rule. The identity goes with it because the backend
// attributes the rule to whoever saved it — `created_by`.
export const POST = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
