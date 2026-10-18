// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// modelSettingsApi.listModels — the provider's model ids, for the picker.
export const POST = route(async (req) => proxyToBackend(req));
