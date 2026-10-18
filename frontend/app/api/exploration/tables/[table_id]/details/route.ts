// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { proxyToBackend } from '@/lib/server/proxy-backend';
import { route } from '@/lib/server/route';

// explorationApi.getTableExplorationDetails — columns-adjacent SQL and Term details for one table.
export const GET = route((req) => proxyToBackend(req));
