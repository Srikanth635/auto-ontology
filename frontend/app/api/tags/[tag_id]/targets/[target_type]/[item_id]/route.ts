// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// tagsApi.detach — take a tag off one object.
export const DELETE = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
