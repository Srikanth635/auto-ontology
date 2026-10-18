// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// modelSettingsApi.getAll — every model role's effective setting.
// API keys never leave the backend; the answer says only whether one is stored.
export const GET = route(async (req) => proxyToBackend(req));
