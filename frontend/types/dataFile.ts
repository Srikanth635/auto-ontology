// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export type DataFileStatus =
	| 'pending'
	| 'converting'
	| 'ingesting'
	| 'ready'
	| 'missing'
	| 'failed';

/** A database file in the data folder, and how far along loading it is. */
export type DataFile = {
	name: string;
	kind: string;
	size_bytes: number | null;
	modified_at: number | null;
	database_name: string | null;
	status: DataFileStatus;
	error: string | null;
};
