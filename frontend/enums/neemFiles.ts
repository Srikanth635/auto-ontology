// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Where a file in the NEEM folder has got to, as the ingestion service reports it. */
export enum NeemFileState {
	/** Still changing (being copied in), or not looked at yet. */
	Waiting = 'waiting',
	Loading = 'loading',
	Loaded = 'loaded',
	Failed = 'failed',
	/** The ingestion service could not be asked. */
	Unknown = 'unknown',
}
