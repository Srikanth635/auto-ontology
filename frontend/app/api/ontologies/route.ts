// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// ontologiesApi.list — every stored ontology with counts and index status.
export const GET = route((req) => proxyToBackend(req));

// ontologiesApi.create — parse and index an ontology sent as source text.
export const POST = route((req) => proxyToBackend(req));
