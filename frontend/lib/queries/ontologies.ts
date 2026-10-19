// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Where OntoQuerying's reads live in the query cache.
 *
 * Everything under one ontology shares the `['ontologies', id]` prefix, so a
 * change to it (an addition, a reindex, a reasoner run) invalidates its
 * summary, element list and element details together.
 */

import { queryOptions } from '@tanstack/react-query';

import { ontologiesApi } from '@/api/ontologies';
import type { KindFilter } from '@/enums/ontologies';

const unwrap = <T>(res: T & { error?: boolean; message?: string }, fallback: string): T => {
	if (res.error) throw new Error(res.message ?? fallback);
	return res;
};

export const ontologyKeys = {
	all: ['ontologies'] as const,
	one: (id: string) => ['ontologies', id] as const,
};

export const ontologyQueries = {
	list: () =>
		queryOptions({
			queryKey: [...ontologyKeys.all, 'list'],
			queryFn: async () =>
				unwrap(await ontologiesApi.list(), 'Failed to load ontologies.').ontologies,
		}),

	reasoners: () =>
		queryOptions({
			queryKey: [...ontologyKeys.all, 'reasoners'],
			queryFn: async () =>
				unwrap(await ontologiesApi.reasoners(), 'Failed to load reasoners.'),
			staleTime: 5 * 60_000,
		}),

	summary: (id: string) =>
		queryOptions({
			queryKey: [...ontologyKeys.one(id), 'summary'],
			queryFn: async () =>
				unwrap(await ontologiesApi.get(id), 'Failed to load the ontology.'),
		}),

	elements: (id: string, filter: KindFilter, q: string) =>
		queryOptions({
			queryKey: [...ontologyKeys.one(id), 'elements', filter, q],
			queryFn: async () =>
				unwrap(
					await ontologiesApi.elements(id, filter, q, 500),
					'Failed to load elements.',
				),
			placeholderData: (previous) => previous,
		}),

	element: (id: string, iri: string) =>
		queryOptions({
			queryKey: [...ontologyKeys.one(id), 'element', iri],
			queryFn: async () => unwrap(await ontologiesApi.element(id, iri), 'Element not found.'),
		}),

	lastReasoning: (id: string) =>
		queryOptions({
			queryKey: [...ontologyKeys.one(id), 'reasoning'],
			queryFn: async () =>
				unwrap(await ontologiesApi.lastReasoning(id), 'Failed to load reasoning.').result,
		}),
};
