// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withPermission } from '@/auth/with-auth';
import { proxyToBackend } from '@/auth/proxy-backend';

// modelSettingsApi.listModels — the provider's model ids, for the picker.
export const POST = withPermission({ modelSettings: ['manage'] })(async (req) =>
	proxyToBackend(req),
);
