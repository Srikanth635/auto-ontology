// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { proxyToBackend } from '@/lib/server/proxy-backend';
import { route } from '@/lib/server/route';

// explorationApi.getSemanticLinkPath — the real hop chain connecting two terms, for
// highlighting a clicked term↔term edge on the graph.
export const GET = route((req) => proxyToBackend(req));
