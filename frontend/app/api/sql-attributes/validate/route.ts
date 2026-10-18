// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// Validate a SQL expression without writing it. Catalog read is enough.
// Creating an attribute and saving one both require catalog:edit.
export const POST = route((req) => proxyToBackend(req));
