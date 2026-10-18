// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// List or add PQL analyses.
export const GET = route((req) => proxyToBackend(req));
export const POST = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
