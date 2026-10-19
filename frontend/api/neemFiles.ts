// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { requests } from './requests';
import type { NeemFile, NeemFolder } from '@/types/neemFiles';

const fileUrl = (name: string) => `neem-files/${encodeURIComponent(name)}`;

export const neemFilesApi = {
	list: () => requests.get<NeemFolder>('neem-files'),

	/** Sends the file's raw bytes; `onProgress` gets 0..1 as they go. */
	upload: (file: File, onProgress?: (fraction: number) => void) =>
		requests.putFile<NeemFile>(fileUrl(file.name), file, onProgress),

	remove: (name: string) => requests.delete<{ status: string }>(fileUrl(name)),
};
