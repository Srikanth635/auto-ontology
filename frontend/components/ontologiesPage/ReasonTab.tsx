// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { ontologiesApi } from '@/api/ontologies';
import { Button } from '@/common/Button';
import { ReasonerBackend } from '@/enums/ontologies';
import { ontologyKeys, ontologyQueries } from '@/lib/queries/ontologies';
import type { OntoRef, ReasonersResponse, ReasoningResult } from '@/types/ontologies';

import { useAddTriples, type Notify } from './hooks';
import {
	CodeBlock,
	ErrorNote,
	InfoNote,
	Panel,
	ReasonerSelect,
	RefChip,
	RefList,
	StatTile,
	reasonerName,
} from './ui';

const PairList = ({
	title,
	pairs,
	joiner,
	onOpen,
	total,
}: {
	title: string;
	pairs: [OntoRef, OntoRef, OntoRef?][];
	joiner: string;
	onOpen: (iri: string) => void;
	total: number;
}) =>
	pairs.length === 0 ? null : (
		<Panel
			title={title}
			description={total > pairs.length ? `First ${pairs.length} of ${total}.` : undefined}
		>
			<ul className="flex flex-col gap-1.5">
				{pairs.map(([a, b, c], i) => (
					<li
						key={i}
						className="flex flex-wrap items-center gap-1.5 text-xs text-secondary"
					>
						<RefChip value={a} onOpen={onOpen} />
						<span className="dark:text-slate-500">{joiner}</span>
						<RefChip value={b} onOpen={onOpen} />
						{c && <RefChip value={c} onOpen={onOpen} />}
					</li>
				))}
			</ul>
		</Panel>
	);

const BackendHelp = ({ reasoners }: { reasoners: ReasonersResponse | null }): ReactNode => {
	const hermit = reasoners?.backends.hermit;
	return (
		<ul className="flex list-disc flex-col gap-1 pl-4 text-xs text-secondary dark:text-slate-400">
			<li>
				<strong className="font-medium text-body dark:text-slate-300">OWL RL</strong> — fast
				rules in pure Python. Finds types from domains and ranges, inverse and transitive
				facts, and disjointness clashes. It cannot classify classes under defined classes.
			</li>
			<li>
				<strong className="font-medium text-body dark:text-slate-300">HermiT</strong> — a
				complete OWL DL reasoner: full classification and unsatisfiable classes.{' '}
				{hermit && !hermit.available ? (
					<span className="text-amber-700 dark:text-amber-300">
						Not available here: {hermit.reason ?? 'Java was not found.'}
					</span>
				) : (
					'Available.'
				)}
			</li>
			<li>
				<strong className="font-medium text-body dark:text-slate-300">Auto</strong> uses
				HermiT when it can, OWL RL otherwise.
			</li>
		</ul>
	);
};

const ResultView = ({
	result,
	onOpen,
	onApply,
	applying,
}: {
	result: ReasoningResult;
	onOpen: (iri: string) => void;
	onApply: () => void;
	applying: boolean;
}) => {
	const c = result.counts;
	const backendName = reasonerName(result.backend);
	return (
		<div className="flex flex-col gap-5">
			<div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
				<StatTile
					label="Consistent"
					value={result.consistent ? 'Yes' : 'No'}
					tone={result.consistent ? 'good' : 'bad'}
				/>
				<StatTile
					label="Unsatisfiable classes"
					value={result.unsatisfiable.length}
					tone={result.unsatisfiable.length ? 'bad' : 'neutral'}
				/>
				<StatTile label="New parents" value={c.new_superclasses ?? 0} />
				<StatTile label="New classes of individuals" value={c.new_types ?? 0} />
				<StatTile label="New facts" value={c.new_property_values ?? 0} />
				<StatTile label={`${backendName} took`} value={`${result.seconds.toFixed(1)}s`} />
			</div>

			{!result.consistent && (
				<ErrorNote
					message={`The ontology is inconsistent, so nothing it implies can be trusted. ${result.errors.join(' ')}`}
				/>
			)}

			{result.unsatisfiable.length > 0 && (
				<Panel
					title="Unsatisfiable classes"
					description="No individual can belong to these: their axioms contradict each other. Usually a modelling mistake."
				>
					<RefList values={result.unsatisfiable} onOpen={onOpen} />
				</Panel>
			)}

			<PairList
				title="Inferred parents"
				joiner="is a"
				onOpen={onOpen}
				total={c.new_superclasses ?? 0}
				pairs={result.new_superclasses.map((p) => [p.sub, p.sup])}
			/>
			<PairList
				title="Inferred equivalences"
				joiner="≡"
				onOpen={onOpen}
				total={c.new_equivalences ?? 0}
				pairs={result.new_equivalences.map((p) => [p.a, p.b])}
			/>
			<PairList
				title="Inferred classes of individuals"
				joiner="is a"
				onOpen={onOpen}
				total={c.new_types ?? 0}
				pairs={result.new_types.map((p) => [p.individual, p.type])}
			/>
			<PairList
				title="Inferred facts"
				joiner=""
				onOpen={onOpen}
				total={c.new_property_values ?? 0}
				pairs={result.new_property_values.map((p) => [p.subject, p.property, p.object])}
			/>
			<PairList
				title="Inferred parent properties"
				joiner="is a"
				onOpen={onOpen}
				total={c.new_superproperties ?? 0}
				pairs={result.new_superproperties.map((p) => [p.sub, p.sup])}
			/>

			{result.consistent &&
				result.inferred_triples === 0 &&
				result.unsatisfiable.length === 0 && (
					<InfoNote>
						{backendName} inferred nothing beyond what the ontology already states.
						{result.backend === 'owlrl' &&
							' OWL RL is incomplete for defined classes; HermiT may find more.'}
					</InfoNote>
				)}

			{result.turtle && (
				<div className="flex flex-col gap-2">
					<CodeBlock
						code={result.turtle}
						label="Inferences as Turtle"
						onApply={onApply}
						applyLabel="Assert in ontology"
						applying={applying}
					/>
					<p className="text-xs text-secondary dark:text-slate-400">
						You don&apos;t need to assert them to use them: questions and SPARQL can
						include inferences directly. Asserting writes them into the working copy as
						stated facts.
					</p>
				</div>
			)}
		</div>
	);
};

export const ReasonTab = ({
	ontologyId,
	reasoners,
	onOpen,
	notify,
}: {
	ontologyId: string;
	reasoners: ReasonersResponse | null;
	onOpen: (iri: string) => void;
	notify: Notify;
}) => {
	const queryClient = useQueryClient();
	const [backend, setBackend] = useState(ReasonerBackend.Auto);
	const [running, setRunning] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [asserted, setAsserted] = useState(false);
	const last = useQuery(ontologyQueries.lastReasoning(ontologyId));
	const { apply, applying } = useAddTriples(ontologyId, notify);

	const run = async () => {
		setRunning(true);
		setError(null);
		const res = await ontologiesApi.reason(ontologyId, backend);
		setRunning(false);
		if (res.error) {
			setError(res.message ?? 'The reasoner failed.');
			return;
		}
		queryClient.setQueryData(ontologyQueries.lastReasoning(ontologyId).queryKey, res);
		// The summary and element details show reasoning status too.
		void queryClient.invalidateQueries({ queryKey: ontologyKeys.one(ontologyId) });
	};

	return (
		<div className="flex flex-col gap-5 p-6">
			<Panel
				title="Run an OWL reasoner"
				description="Checks the ontology is consistent, finds classes that cannot have members, and works out what the axioms imply."
				actions={
					<>
						<ReasonerSelect
							value={backend}
							onChange={setBackend}
							reasoners={reasoners}
						/>
						<Button onClick={run} loading={running}>
							Run
						</Button>
					</>
				}
			>
				<BackendHelp reasoners={reasoners} />
			</Panel>
			{running && (
				<InfoNote>
					Reasoning… Small ontologies take seconds; large OWL DL ontologies can take
					minutes with HermiT.
				</InfoNote>
			)}
			<ErrorNote message={error ?? (last.error ? last.error.message : null)} />
			{asserted && last.data === null && !running && (
				<InfoNote>
					The inferences are now stated in the ontology. Any change clears the last
					result; run the reasoner again to check the new version.
				</InfoNote>
			)}
			{last.data && (
				<ResultView
					result={last.data}
					onOpen={onOpen}
					onApply={async () => {
						if (await apply(last.data!.turtle, 'reasoning')) setAsserted(true);
					}}
					applying={applying === 'reasoning'}
				/>
			)}
		</div>
	);
};
