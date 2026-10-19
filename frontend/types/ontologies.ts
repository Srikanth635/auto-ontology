// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CandidateRelation, ElementKind, ReasonerBackend } from '@/enums/ontologies';

/** An IRI with its display name. */
export type OntoRef = { iri: string; name: string };

export type OntologyCounts = {
	class: number;
	object_property: number;
	datatype_property: number;
	annotation_property: number;
	individual: number;
	triples: number;
};

export type IndexStatus = {
	dense: boolean;
	vector_store: string;
	embedded: number;
	reused: number;
	warnings: string[];
};

export type ReasoningSummary = {
	backend: string;
	consistent: boolean;
	unsatisfiable: number;
	inferred_triples: number;
};

export type OntologySummary = {
	id: string;
	title: string;
	filename: string;
	created_at: string;
	updated_at: string;
	ontology_iri?: string;
	/** Absent until the ontology has been loaded in this backend process. */
	counts?: OntologyCounts;
	index?: IndexStatus;
	reasoning?: ReasoningSummary | null;
	loaded?: boolean;
	prefixes?: Record<string, string>;
};

export type ReasonerInfo = {
	available: boolean;
	profile: string;
	reason?: string;
};

export type ReasonersResponse = {
	default: string;
	backends: Record<Exclude<ReasonerBackend, ReasonerBackend.Auto>, ReasonerInfo>;
};

export type ElementListItem = {
	iri: string;
	name: string;
	kind: ElementKind;
	definition: string;
};

export type ElementDetail = {
	iri: string;
	kind: ElementKind;
	name: string;
	alt_labels: string[];
	definition: string;
	comment: string;
	parents: OntoRef[];
	children: OntoRef[];
	equivalents: OntoRef[];
	disjoint_with: OntoRef[];
	restrictions: string[];
	domain: OntoRef[];
	range: OntoRef[];
	inverse_of: OntoRef[];
	characteristics: string[];
	types: OntoRef[];
	assertions: { property: string; property_name: string; value: string }[];
	deprecated: boolean;
	path: string[];
	document: string;
	inferred: {
		backend: string;
		superclasses: OntoRef[];
		types: OntoRef[];
		unsatisfiable: boolean;
	} | null;
};

export type SearchHit = {
	iri: string;
	name: string;
	kind: ElementKind;
	definition: string;
	path: string[];
	score: number;
	dense_rank: number | null;
	keyword_rank: number | null;
	rerank_score: number | null;
};

export type SearchResponse = {
	query: string;
	reranker: string;
	dense: boolean;
	results: SearchHit[];
};

/** One RDF term in a SPARQL result. */
export type SparqlTerm = {
	type: 'iri' | 'literal' | 'bnode';
	value: string;
	name?: string;
	datatype?: string;
	lang?: string;
};

export type SparqlResult =
	| {
			type: 'select';
			variables: string[];
			rows: Record<string, SparqlTerm | null>[];
			truncated: boolean;
	  }
	| { type: 'ask'; boolean: boolean }
	| { type: 'graph'; triple_count: number; triples: (SparqlTerm | null)[][]; truncated: boolean };

export type QueryCheck = {
	ok: boolean;
	errors: string[];
	warnings: string[];
	iris: string[];
};

export type ReasoningUse = { backend: string; consistent: boolean; note?: string } | null;

export type SparqlResponse = {
	check: QueryCheck;
	result: SparqlResult | null;
	reasoning: ReasoningUse;
};

export type AskAttempt = {
	attempt: number;
	sparql: string;
	explanation: string;
	check?: QueryCheck;
	error?: string;
	rows?: number;
};

export type AskResponse = {
	question: string;
	answerable: boolean;
	answer: string;
	sparql: string;
	explanation: string;
	result: SparqlResult | null;
	attempts: AskAttempt[];
	context: {
		mentions: { text: string; kind: string }[];
		reranker: string;
		elements: { iri: string; name: string; kind: ElementKind }[];
	};
	reasoning: ReasoningUse;
};

export type Candidate = {
	iri: string;
	name: string;
	kind: ElementKind;
	definition: string;
	path: string[];
	retrieval_rank: number;
	relation?: CandidateRelation;
	confidence?: number;
	reason?: string;
};

export type CandidatesResponse = {
	description: string;
	reranker: string;
	judged: boolean;
	suitable_exists: boolean | null;
	summary: string;
	warnings: string[];
	candidates: Candidate[];
};

export type PlacementResponse = {
	name: string;
	existing_equivalent: (OntoRef & { reason: string }) | null;
	proposed_iri: string | null;
	label: string;
	definition: string;
	alt_labels: string[];
	parents: (OntoRef & { path: string[]; reason: string })[];
	suggested_restrictions: string[];
	confidence: number;
	turtle: string;
};

export type ChildSuggestion = {
	label: string;
	definition: string;
	reason: string;
	possibly_existing: OntoRef[];
	proposed_iri: string;
	turtle: string;
};

export type ChildrenResponse = { iri: string; name: string; suggestions: ChildSuggestion[] };

export type DefinitionDraft = OntoRef & { definition: string; turtle: string };

export type DefinitionsResponse = { definitions: DefinitionDraft[]; predicate: string };

export type DuplicatePair = {
	a: OntoRef;
	b: OntoRef;
	relation: string;
	evidence: string[];
	similarity?: number;
	verdict?: 'same' | 'one_is_kind_of_other' | 'distinct';
	reason?: string;
};

export type IssuesResponse = {
	duplicates: DuplicatePair[];
	missing_definitions: OntoRef[];
	missing_labels: OntoRef[];
	root_classes: OntoRef[];
	single_child_classes: (OntoRef & { child: OntoRef })[];
	properties_without_domain: OntoRef[];
	properties_without_range: OntoRef[];
	hierarchy_cycles: OntoRef[];
	deprecated_parents: OntoRef[];
	warnings: string[];
};

export type AdditionsResponse = OntologySummary & { added_triples: number };

export type ReasoningResult = {
	backend: string;
	consistent: boolean;
	seconds: number;
	errors: string[];
	unsatisfiable: OntoRef[];
	inferred_triples: number;
	new_superclasses: { sub: OntoRef; sup: OntoRef }[];
	new_equivalences: { a: OntoRef; b: OntoRef }[];
	new_types: { individual: OntoRef; type: OntoRef }[];
	new_property_values: { subject: OntoRef; property: OntoRef; object: OntoRef }[];
	new_superproperties: { sub: OntoRef; sup: OntoRef }[];
	counts: Record<string, number>;
	turtle: string;
};

export type Mapping = {
	source: OntoRef;
	target: OntoRef;
	relation: 'equivalent' | 'broader' | 'narrower' | 'related';
	confidence: number;
	reason: string;
	label_match: boolean;
	kind: string;
};

export type AlignResponse = {
	source: string;
	target: string;
	judged: boolean;
	total_sources: number;
	offset: number;
	processed: number;
	next_offset: number | null;
	mappings: Mapping[];
	unmatched: OntoRef[];
	warnings: string[];
	sssom_tsv: string;
	turtle: string;
};

export type DerivedShapesResponse = { turtle: string; rules: string[] };

export type RulesShapesResponse = {
	rules: string[];
	turtle: string;
	notes: string[];
	ok: boolean;
	problems: string[];
};

export type ValidationResultItem = {
	focus_node: string | null;
	focus_name: string | null;
	path: string | null;
	path_name: string | null;
	value: string | null;
	severity: string;
	message: string;
	constraint: string;
	shape: string | null;
};

export type ValidationResponse = {
	source: string;
	conforms: boolean;
	violations: number;
	warnings: number;
	results: ValidationResultItem[];
	derived_rules: string[];
	explanation: string;
};
