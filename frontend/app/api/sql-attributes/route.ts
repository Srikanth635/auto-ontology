// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// Create a SqlAttribute. The identity is recorded as `created_by`.
export const POST = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
