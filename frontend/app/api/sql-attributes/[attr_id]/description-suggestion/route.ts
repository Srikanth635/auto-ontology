// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// LLM-assisted description suggestion, offered from the SqlAttribute edit
// flow. The generated text is cached on the attribute, so the caller's
// identity goes with the request.
export const GET = route((req, { user }) => proxyToBackend(req, { userId: user.id }));
