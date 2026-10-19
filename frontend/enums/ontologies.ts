// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** The workspace tabs of one ontology, as they appear in `?tab=`. */
export enum OntologyTab {
	Explore = 'explore',
	Ask = 'ask',
	Find = 'find',
	Grow = 'grow',
	Reason = 'reason',
	Align = 'align',
	Validate = 'validate',
}

/** Element kinds as the backend names them. */
export enum ElementKind {
	Class = 'class',
	ObjectProperty = 'object_property',
	DatatypeProperty = 'datatype_property',
	AnnotationProperty = 'annotation_property',
	Individual = 'individual',
}

/** Kind filters the search and elements routes accept (`property` = all three). */
export enum KindFilter {
	All = '',
	Class = 'class',
	Property = 'property',
	Individual = 'individual',
}

export enum ReasonerBackend {
	Auto = 'auto',
	OwlRl = 'owlrl',
	Hermit = 'hermit',
}

/** How a candidate relates to what was described. */
export enum CandidateRelation {
	Exact = 'exact',
	Narrower = 'narrower',
	Broader = 'broader',
	Related = 'related',
	Unrelated = 'unrelated',
}

export enum ExportFormat {
	Turtle = 'turtle',
	RdfXml = 'xml',
	NTriples = 'nt',
	JsonLd = 'json-ld',
}
