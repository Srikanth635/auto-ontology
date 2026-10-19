// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// Multipart upload of an ontology file, for scripts. The UI sends the file's
// text to `POST /api/ontologies` instead, since this proxy relays bodies as text.
export const POST = route((req) => proxyToBackend(req));
