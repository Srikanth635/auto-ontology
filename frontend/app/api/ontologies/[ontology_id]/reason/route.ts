// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// ontologiesApi.lastReasoning — the kept reasoning result, if any.
export const GET = route((req) => proxyToBackend(req));

// ontologiesApi.reason — run OWL RL or HermiT over the ontology.
export const POST = route((req) => proxyToBackend(req));
