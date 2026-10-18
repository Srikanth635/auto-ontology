// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { proxyToBackend } from '@/lib/server/proxy-backend';
import { route } from '@/lib/server/route';

// explorationApi.getSqlExplorationDetails — the CustomAnalysis, Column, Table and SqlAttribute nodes hanging off this Sql node, for expanding it on the graph.
export const GET = route((req) => proxyToBackend(req));
