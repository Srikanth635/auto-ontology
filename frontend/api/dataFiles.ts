// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { requests } from './requests';
import type { DataFile } from '@/types/dataFile';
import type { ApiResponse, ResponseWithError } from './types';

const fileUrl = (name: string) => `connections/files/${encodeURIComponent(name)}`;

export const dataFilesApi = {
	list: (): Promise<ApiResponse<DataFile[]>> =>
		requests.get<{ data: DataFile[]; count: number }>('connections/files'),

	/** Stores the file in the data folder; ingestion starts on its own from there. */
	upload: (
		file: File,
		onProgress?: (fraction: number) => void,
	): Promise<ResponseWithError<{ data: DataFile }>> =>
		requests.putFile<{ data: DataFile }>(fileUrl(file.name), file, onProgress),

	/** Deletes the file and the database loaded from it. */
	remove: (name: string) => requests.delete<{ data: { database_name: string } }>(fileUrl(name)),
};
