// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// Grade how well the semantic layer covers the entities in a free-text
// question. Same retrieval capability as chat, so it is gated on
// `chat: ['use']`.
export const POST = route((req) => proxyToBackend(req));
