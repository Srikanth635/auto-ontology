// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';
import { withTagAuthors } from '@/lib/tagAuthors';

// sqlAttributesApi.get — fetch one SqlAttribute node, with created_by /
// modified_by named so the side panel can show them.
export const GET = route(async (req) => withTagAuthors(await proxyToBackend(req)));

// Replace a SqlAttribute's SQL.
export const PUT = route((req, { user }) => proxyToBackend(req, { userId: user.id }));

// Patch name, description, or certification.
export const PATCH = route((req, { user }) => proxyToBackend(req, { userId: user.id }));

// Delete a SqlAttribute.
export const DELETE = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
