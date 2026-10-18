// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';
import { withTagAuthors } from '@/lib/tagAuthors';

// termsApi.getColumnAttributes — ColumnAttribute nodes for one term (with
// primary/referenced columns). Authors ride along so the side panel can name
// who last edited each attribute.
export const GET = route(async (req) => withTagAuthors(await proxyToBackend(req)));
