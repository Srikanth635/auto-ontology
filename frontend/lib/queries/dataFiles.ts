// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { queryOptions } from '@tanstack/react-query';

import { dataFilesApi } from '@/api/dataFiles';
import type { DataFile } from '@/types/dataFile';

/** How often the list is re-read while a file is still on its way in. */
const BUSY_REFETCH_MS = 3000;

const isBusy = (file: DataFile) =>
	file.status === 'pending' || file.status === 'converting' || file.status === 'ingesting';

export const dataFileQueries = {
	list: () =>
		queryOptions({
			queryKey: ['data-files', 'list'] as const,
			queryFn: async (): Promise<DataFile[]> => {
				const res = await dataFilesApi.list();
				if (res.error) throw new Error(res.message ?? 'Failed to load data files.');
				return res.data ?? [];
			},
			// Ingestion happens in another service, so progress is only visible by
			// asking again. Stops once everything has settled.
			refetchInterval: (query) => (query.state.data?.some(isBusy) ? BUSY_REFETCH_MS : false),
		}),
};
