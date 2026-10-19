// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { ontologiesApi } from '@/api/ontologies';
import { ontologyKeys } from '@/lib/queries/ontologies';

/** What an action reports back to the workspace's toast. */
export type Notify = (message: string, ok?: boolean) => void;

/**
 * Add reviewed Turtle to an ontology, then refresh everything cached about it
 * -- an addition rebuilds the ontology and drops its reasoning result.
 */
export const useAddTriples = (ontologyId: string, notify: Notify) => {
	const queryClient = useQueryClient();
	const [applying, setApplying] = useState<string | null>(null);

	const apply = useCallback(
		async (turtle: string, key = 'default'): Promise<boolean> => {
			setApplying(key);
			const res = await ontologiesApi.addTriples(ontologyId, turtle);
			setApplying(null);
			if (res.error) {
				notify(res.message ?? 'Could not add the triples.', false);
				return false;
			}
			notify(
				res.added_triples === 0
					? 'Nothing new: the ontology already had all of it.'
					: `Added ${res.added_triples} triple${res.added_triples === 1 ? '' : 's'}.`,
				true,
			);
			await Promise.all([
				queryClient.invalidateQueries({ queryKey: ontologyKeys.one(ontologyId) }),
				queryClient.invalidateQueries({ queryKey: [...ontologyKeys.all, 'list'] }),
			]);
			return true;
		},
		[ontologyId, notify, queryClient],
	);

	return { apply, applying };
};

/**
 * Run an async request with its own loading and error state, keeping the last
 * successful result. `run` resolves to the result, or null on failure.
 */
export const useRequest = <T>() => {
	const [data, setData] = useState<T | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(false);

	const run = useCallback(
		async (request: () => Promise<T & { error?: boolean; message?: string }>) => {
			setLoading(true);
			setError(null);
			const res = await request();
			setLoading(false);
			if (res.error) {
				setError(res.message ?? 'The request failed.');
				return null;
			}
			setData(res);
			return res as T;
		},
		[],
	);

	return { data, error, loading, run, setData };
};
