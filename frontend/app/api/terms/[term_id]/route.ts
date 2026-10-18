// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';
import { withTagAuthors } from '@/lib/tagAuthors';

// termsApi.getById — fetch one Term node. Authors are resolved here so Last
// Modified can name the person who saved it.
export const GET = route(async (req) => withTagAuthors(await proxyToBackend(req)));

// termsApi.update — edit a Term. The identity is recorded as `modified_by`.
export const PATCH = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
