// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withPermission } from '@/auth/with-auth';
import { proxyToBackend } from '@/auth/proxy-backend';

// modelSettingsApi.test — one small real call with an unsaved setting. The
// folder is `verify`, not `test`: .dockerignore drops every `test` directory.
// Manage,
// not read: it can use the stored key, and it spends the provider's quota.
export const POST = withPermission({ modelSettings: ['manage'] })(async (req) =>
	proxyToBackend(req),
);
