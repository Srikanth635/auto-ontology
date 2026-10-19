// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { NeemFileState } from '@/enums/neemFiles';

export type NeemFile = {
	name: string;
	size: number;
	modified_at: string;
	state: NeemFileState;
	error?: string | null;
	rows?: number | null;
};

export type NeemFolder = {
	/** False when no NEEM folder is configured (NEEM_DATA_DIR unset). */
	enabled: boolean;
	/** The database every NEEM is merged into. */
	database: string;
	/** `ingesting` while the merged database is being re-read into the catalog. */
	catalog: string;
	max_upload_bytes: number;
	files: NeemFile[];
};
