// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withPermission } from '@/auth/with-auth';
import { proxyToBackend } from '@/auth/proxy-backend';

// modelSettingsApi.reembedStatus — whether vectors are being rebuilt.
export const GET = withPermission({ modelSettings: ['read'] })(async (req) => proxyToBackend(req));

// modelSettingsApi.reembed — rebuild every vector with the current embedding model.
export const POST = withPermission({ modelSettings: ['manage'] })(async (req) =>
	proxyToBackend(req),
);
