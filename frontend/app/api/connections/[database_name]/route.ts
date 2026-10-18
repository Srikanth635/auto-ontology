// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// connectionsApi.update — rewrite a connection's settings.
export const PUT = route((req) => proxyToBackend(req));

// connectionsApi.delete — remove a connection.
export const DELETE = route((req) => proxyToBackend(req));
