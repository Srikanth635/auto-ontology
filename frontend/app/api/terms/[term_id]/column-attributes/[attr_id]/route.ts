// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// Updating a ColumnAttribute changes only name/description; backend refreshes
// the corresponding semantic VDB embedding.
export const PATCH = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
