// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// datasources.updateNode — edit mutable properties of a catalog node.
export const PATCH = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
