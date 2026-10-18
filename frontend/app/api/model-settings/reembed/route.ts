// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// modelSettingsApi.reembedStatus — whether vectors are being rebuilt.
export const GET = route(async (req) => proxyToBackend(req));

// modelSettingsApi.reembed — rebuild every vector with the current embedding model.
export const POST = route(async (req) => proxyToBackend(req));
