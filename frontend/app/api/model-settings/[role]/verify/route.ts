// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// modelSettingsApi.test — one small real call with an unsaved setting. The
// folder is `verify`, not `test`: .dockerignore drops every `test` directory.
// Manage,
// not read: it can use the stored key, and it spends the provider's quota.
export const POST = route(async (req) => proxyToBackend(req));
