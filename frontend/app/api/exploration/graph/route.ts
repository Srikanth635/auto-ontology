// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// explorationApi.getDataExplorationGraph — full data-layer graph ({nodes, links}).
export const GET = route((req) => proxyToBackend(req));
