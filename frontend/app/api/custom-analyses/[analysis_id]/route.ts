// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// Edit or delete a custom analysis.
export const PUT = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
export const DELETE = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
