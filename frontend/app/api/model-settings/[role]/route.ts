// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withPermission } from '@/auth/with-auth';
import { proxyToBackend } from '@/auth/proxy-backend';

// modelSettingsApi.save — choose a role's provider and model. The key is stored
// encrypted, and the caller is recorded as the one who changed it.
export const PUT = withPermission({ modelSettings: ['manage'] })(async (req, { user }) =>
	proxyToBackend(req, { userId: user.id }),
);

// modelSettingsApi.reset — forget a role's saved setting.
export const DELETE = withPermission({ modelSettings: ['manage'] })(async (req) =>
	proxyToBackend(req),
);
