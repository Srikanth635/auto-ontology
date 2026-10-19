// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// Download link target: the working copy as Turtle, RDF/XML, N-Triples or JSON-LD.
export const GET = route((req) => proxyToBackend(req));
