// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { requests } from './requests';
import type { ExportFormat, KindFilter, ReasonerBackend } from '@/enums/ontologies';
import type {
	AdditionsResponse,
	AlignResponse,
	AskResponse,
	CandidatesResponse,
	ChildrenResponse,
	DefinitionsResponse,
	DerivedShapesResponse,
	ElementDetail,
	ElementListItem,
	IssuesResponse,
	OntologySummary,
	PlacementResponse,
	ReasonersResponse,
	ReasoningResult,
	RulesShapesResponse,
	SearchResponse,
	SparqlResponse,
	ValidationResponse,
} from '@/types/ontologies';

const base = (id: string) => `/ontologies/${encodeURIComponent(id)}`;

const kinds = (filter: KindFilter): string[] | undefined => (filter ? [filter] : undefined);

export const ontologiesApi = {
	list: () => requests.get<{ ontologies: OntologySummary[]; reranker: string }>('/ontologies'),

	/** The file's text goes in the body; the proxy relays bodies as text. */
	create: (content: string, filename: string, title = '') =>
		requests.post<OntologySummary>('/ontologies', { content, filename, title }),

	get: (id: string) => requests.get<OntologySummary>(base(id)),

	remove: (id: string) => requests.delete<{ deleted: string }>(base(id)),

	reindex: (id: string) => requests.post<OntologySummary['index']>(`${base(id)}/reindex`),

	/** A download URL rather than a request: the browser saves the file. */
	exportUrl: (id: string, format: ExportFormat) =>
		`/api${base(id)}/export?format=${encodeURIComponent(format)}`,

	reasoners: () => requests.get<ReasonersResponse>('/ontologies/reasoners'),

	elements: (id: string, filter: KindFilter, q: string, limit = 200) =>
		requests.get<{ total: number; elements: ElementListItem[] }>(`${base(id)}/elements`, {
			...(filter ? { kind: filter } : {}),
			...(q ? { q } : {}),
			limit,
		}),

	element: (id: string, iri: string) =>
		requests.get<ElementDetail>(`${base(id)}/element`, { iri }),

	search: (id: string, query: string, filter: KindFilter, k = 20) =>
		requests.post<SearchResponse>(`${base(id)}/search`, { query, k, kinds: kinds(filter) }),

	candidates: (id: string, description: string, filter: KindFilter, judge: boolean) =>
		requests.post<CandidatesResponse>(`${base(id)}/candidates`, {
			description,
			kinds: kinds(filter),
			judge,
		}),

	ask: (id: string, question: string, useInferences: boolean, reasoner: ReasonerBackend) =>
		requests.post<AskResponse>(`${base(id)}/ask`, {
			question,
			use_inferences: useInferences,
			reasoner,
		}),

	sparql: (id: string, query: string, useInferences: boolean, reasoner: ReasonerBackend) =>
		requests.post<SparqlResponse>(`${base(id)}/sparql`, {
			query,
			use_inferences: useInferences,
			reasoner,
		}),

	reason: (id: string, backend: ReasonerBackend) =>
		requests.post<ReasoningResult>(`${base(id)}/reason`, { backend }),

	lastReasoning: (id: string) =>
		requests.get<{ result: ReasoningResult | null }>(`${base(id)}/reason`),

	placement: (id: string, name: string, description: string) =>
		requests.post<PlacementResponse>(`${base(id)}/grow/placement`, { name, description }),

	children: (id: string, iri: string, limit = 5) =>
		requests.post<ChildrenResponse>(`${base(id)}/grow/children`, { iri, limit }),

	definitions: (id: string, iris?: string[]) =>
		requests.post<DefinitionsResponse>(`${base(id)}/grow/definitions`, { iris }),

	issues: (id: string, confirmDuplicates: boolean) =>
		requests.post<IssuesResponse>(`${base(id)}/grow/issues`, {
			confirm_duplicates: confirmDuplicates,
		}),

	addTriples: (id: string, turtle: string) =>
		requests.post<AdditionsResponse>(`${base(id)}/additions`, { turtle }),

	align: (sourceId: string, targetId: string, judge: boolean, maxSources: number, offset = 0) =>
		requests.post<AlignResponse>('/ontologies/align', {
			source_id: sourceId,
			target_id: targetId,
			judge,
			max_sources: maxSources,
			offset,
		}),

	derivedShapes: (id: string) =>
		requests.get<DerivedShapesResponse>(`${base(id)}/shapes/derived`),

	shapesFromRules: (id: string, rules: string[]) =>
		requests.post<RulesShapesResponse>(`${base(id)}/shapes/from-rules`, { rules }),

	validate: (
		id: string,
		body: { data: string; shapes: string; use_derived: boolean; explain: boolean },
	) => requests.post<ValidationResponse>(`${base(id)}/validate`, body),
};
