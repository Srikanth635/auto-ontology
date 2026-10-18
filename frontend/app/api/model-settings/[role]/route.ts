// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// modelSettingsApi.save — choose a role's provider and model. The key is stored
// encrypted, and the caller is recorded as the one who changed it.
export const PUT = route(async (req, { user }) => proxyToBackend(req, { userId: user.id }));

// modelSettingsApi.reset — forget a role's saved setting.
export const DELETE = route(async (req) => proxyToBackend(req));
