// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// neemFilesApi.upload — the body is the file's raw bytes, streamed through.
export const PUT = route((req) => proxyToBackend(req, { streamBody: true }));
// neemFilesApi.remove — delete a file; its rows leave the merged database.
export const DELETE = route((req) => proxyToBackend(req));
