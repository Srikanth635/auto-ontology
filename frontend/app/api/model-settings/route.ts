// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withPermission } from '@/auth/with-auth';
import { proxyToBackend } from '@/auth/proxy-backend';

// modelSettingsApi.getAll — every model role's effective setting (admin only).
// API keys never leave the backend; the answer says only whether one is stored.
export const GET = withPermission({ modelSettings: ['read'] })(async (req) => proxyToBackend(req));
