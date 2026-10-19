// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// modelInterchangeApi.importModel — upload a native neemontology or Apache Ossie model
// YAML file and apply it to the catalog + semantic layer. Admin-only: can
// replace existing data.
export const POST = route((req) => proxyToBackend(req));
