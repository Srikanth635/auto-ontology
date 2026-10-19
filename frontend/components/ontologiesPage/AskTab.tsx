// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useState } from 'react';

import { ontologiesApi } from '@/api/ontologies';
import { Button } from '@/common/Button';
import { ButtonTheme } from '@/enums/button';
import { ReasonerBackend } from '@/enums/ontologies';
import type {
	AskResponse,
	ReasonersResponse,
	ReasoningUse,
	SparqlResponse,
} from '@/types/ontologies';

import { useRequest } from './hooks';
import {
	CodeBlock,
	Disclosure,
	ErrorNote,
	InfoNote,
	KindBadge,
	Panel,
	ReasonerSelect,
	SparqlResultView,
	ToggleField,
	monoClass,
	reasonerName,
} from './ui';

const STARTER_QUERY = `PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

SELECT ?class ?label WHERE {
  ?class a owl:Class .
  OPTIONAL { ?class rdfs:label ?label }
}
LIMIT 50`;

const InferenceOptions = ({
	use,
	setUse,
	reasoner,
	setReasoner,
	reasoners,
}: {
	use: boolean;
	setUse: (v: boolean) => void;
	reasoner: ReasonerBackend;
	setReasoner: (v: ReasonerBackend) => void;
	reasoners: ReasonersResponse | null;
}) => (
	<div className="flex flex-wrap items-center gap-3">
		<ToggleField label="Include reasoner inferences" checked={use} onChange={setUse} />
		{use && <ReasonerSelect value={reasoner} onChange={setReasoner} reasoners={reasoners} />}
	</div>
);

const ReasoningNote = ({ reasoning }: { reasoning: ReasoningUse }) =>
	reasoning ? (
		<InfoNote>
			{reasoning.consistent
				? `Queried the ontology plus what ${reasonerName(reasoning.backend)} inferred.`
				: (reasoning.note ??
					`${reasonerName(reasoning.backend)} found the ontology inconsistent, so only stated facts were queried.`)}
		</InfoNote>
	) : null;

export const AskTab = ({
	ontologyId,
	reasoners,
	onOpen,
}: {
	ontologyId: string;
	reasoners: ReasonersResponse | null;
	onOpen: (iri: string) => void;
}) => {
	const [question, setQuestion] = useState('');
	const [useInferences, setUseInferences] = useState(false);
	const [reasoner, setReasoner] = useState(ReasonerBackend.Auto);
	const ask = useRequest<AskResponse>();

	const [query, setQuery] = useState(STARTER_QUERY);
	const [sparqlInferences, setSparqlInferences] = useState(false);
	const [sparqlReasoner, setSparqlReasoner] = useState(ReasonerBackend.Auto);
	const sparql = useRequest<SparqlResponse>();

	const submitQuestion = () => {
		if (!question.trim()) return;
		void ask.run(() => ontologiesApi.ask(ontologyId, question.trim(), useInferences, reasoner));
	};

	const answer = ask.data;
	const failedAttempts = answer?.attempts.filter((a) => a.check?.ok === false || a.error) ?? [];

	return (
		<div className="flex flex-col gap-5 p-6">
			<Panel
				title="Ask a question"
				description="Your question is turned into a SPARQL query over the relevant part of the ontology, checked, run, and answered from the results."
			>
				<form
					className="flex flex-col gap-3"
					onSubmit={(e) => {
						e.preventDefault();
						submitQuestion();
					}}
				>
					<textarea
						className={`${monoClass} min-h-20 font-sans text-sm`}
						placeholder="e.g. Which pizzas have a spicy topping?"
						aria-label="Question"
						value={question}
						onChange={(e) => setQuestion(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submitQuestion();
						}}
					/>
					<div className="flex flex-wrap items-center justify-between gap-3">
						<InferenceOptions
							use={useInferences}
							setUse={setUseInferences}
							reasoner={reasoner}
							setReasoner={setReasoner}
							reasoners={reasoners}
						/>
						<Button type="submit" loading={ask.loading} disabled={!question.trim()}>
							Ask
						</Button>
					</div>
				</form>
			</Panel>

			<ErrorNote message={ask.error} />

			{answer && (
				<Panel title="Answer">
					<div className="flex flex-col gap-4">
						<p className="text-sm leading-relaxed whitespace-pre-wrap text-heading dark:text-slate-100">
							{answer.answer}
						</p>
						<ReasoningNote reasoning={answer.reasoning} />
						{answer.result && (
							<SparqlResultView result={answer.result} onOpen={onOpen} />
						)}
						{answer.sparql && (
							<CodeBlock
								code={answer.sparql}
								label="SPARQL"
								onApply={() => {
									setQuery(answer.sparql);
									setSparqlInferences(useInferences);
								}}
								applyLabel="Edit below"
							/>
						)}
						{answer.explanation && (
							<p className="text-xs text-secondary dark:text-slate-400">
								{answer.explanation}
							</p>
						)}
						{answer.context.elements.length > 0 && (
							<Disclosure
								summary={`Based on ${answer.context.elements.length} ontology elements${
									answer.context.mentions.length
										? ` · concepts: ${answer.context.mentions.map((m) => m.text).join(', ')}`
										: ''
								}`}
							>
								<div className="flex flex-wrap gap-1.5">
									{answer.context.elements.map((e) => (
										<button
											key={e.iri}
											type="button"
											onClick={() => onOpen(e.iri)}
											className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-slate-200 px-2 py-0.5 text-xs text-body hover:border-brand dark:border-slate-700 dark:text-slate-300"
										>
											<KindBadge kind={e.kind} />
											{e.name}
										</button>
									))}
								</div>
							</Disclosure>
						)}
						{failedAttempts.length > 0 && (
							<Disclosure
								summary={`${failedAttempts.length} earlier ${
									failedAttempts.length === 1 ? 'query was' : 'queries were'
								} rejected and repaired`}
							>
								<ol className="flex flex-col gap-3">
									{failedAttempts.map((a) => (
										<li key={a.attempt} className="flex flex-col gap-1.5">
											<pre className="overflow-x-auto rounded bg-slate-50 p-2 font-mono text-[11px] dark:bg-slate-800/60">
												{a.sparql}
											</pre>
											<p className="text-xs text-red-700 dark:text-red-300">
												{[...(a.check?.errors ?? []), a.error]
													.filter(Boolean)
													.join(' ')}
											</p>
										</li>
									))}
								</ol>
							</Disclosure>
						)}
					</div>
				</Panel>
			)}

			<Panel
				title="Write SPARQL"
				description="Read-only queries run against this ontology alone; every IRI must exist in it."
			>
				<form
					className="flex flex-col gap-3"
					onSubmit={(e) => {
						e.preventDefault();
						void sparql.run(() =>
							ontologiesApi.sparql(
								ontologyId,
								query,
								sparqlInferences,
								sparqlReasoner,
							),
						);
					}}
				>
					<textarea
						className={`${monoClass} min-h-48`}
						aria-label="SPARQL query"
						spellCheck={false}
						value={query}
						onChange={(e) => setQuery(e.target.value)}
					/>
					<div className="flex flex-wrap items-center justify-between gap-3">
						<InferenceOptions
							use={sparqlInferences}
							setUse={setSparqlInferences}
							reasoner={sparqlReasoner}
							setReasoner={setSparqlReasoner}
							reasoners={reasoners}
						/>
						<div className="flex gap-2">
							<Button
								theme={ButtonTheme.Minimal}
								onClick={() => setQuery(STARTER_QUERY)}
								disabled={query === STARTER_QUERY}
							>
								Reset
							</Button>
							<Button type="submit" loading={sparql.loading} disabled={!query.trim()}>
								Run
							</Button>
						</div>
					</div>
				</form>
				<div className="mt-4 flex flex-col gap-3">
					<ErrorNote message={sparql.error} />
					{sparql.data && !sparql.data.check.ok && (
						<ErrorNote message={sparql.data.check.errors.join(' ')} />
					)}
					{sparql.data?.check.warnings.map((w) => (
						<InfoNote key={w}>{w}</InfoNote>
					))}
					{sparql.data && <ReasoningNote reasoning={sparql.data.reasoning} />}
					{sparql.data?.result && (
						<SparqlResultView result={sparql.data.result} onOpen={onOpen} />
					)}
				</div>
			</Panel>
		</div>
	);
};
