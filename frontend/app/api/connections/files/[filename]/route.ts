// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// The file is the request body, so it is streamed through rather than read.
export const PUT = route((req) => proxyToBackend(req, { streamBody: true }));

export const DELETE = route((req) => proxyToBackend(req));
