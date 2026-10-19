// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// ontologiesApi.get — counts, prefixes, index and reasoning status.
export const GET = route((req) => proxyToBackend(req));

// ontologiesApi.remove — delete the ontology, its files and vectors.
export const DELETE = route((req) => proxyToBackend(req));
