// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { proxyToBackend } from '@/lib/server/proxy-backend';
import { route } from '@/lib/server/route';

// explorationApi.getSqlAttributeExplorationDetails — a SqlAttribute's own Sql query and owning Term, for expanding it on the graph.
export const GET = route((req) => proxyToBackend(req));
