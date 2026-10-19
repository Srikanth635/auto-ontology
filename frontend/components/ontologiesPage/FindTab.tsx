// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useState } from 'react';

import { ontologiesApi } from '@/api/ontologies';
import { Button } from '@/common/Button';
import { KindFilter } from '@/enums/ontologies';
import type { CandidatesResponse, SearchHit, SearchResponse } from '@/types/ontologies';

import { useRequest } from './hooks';
import {
	ErrorNote,
	InfoNote,
	KindBadge,
	KindSelect,
	Panel,
	RelationBadge,
	ToggleField,
	inputClass,
} from './ui';

enum Mode {
	Candidates = 'candidates',
	Search = 'search',
}

const ResultName = ({
	iri,
	name,
	onOpen,
}: {
	iri: string;
	name: string;
	onOpen: (iri: string) => void;
}) => (
	<button
		type="button"
		onClick={() => onOpen(iri)}
		title={iri}
		className="cursor-pointer text-left text-sm font-medium text-heading hover:text-brand-strong hover:underline dark:text-slate-100 dark:hover:text-brand-light"
	>
		{name}
	</button>
);

const Path = ({ path }: { path: string[] }) =>
	path.length > 1 ? (
		<p className="text-[11px] text-secondary dark:text-slate-500">
			{[...path].reverse().join(' › ')}
		</p>
	) : null;

const signals = (hit: SearchHit): string =>
	[
		hit.dense_rank != null ? `meaning #${hit.dense_rank}` : null,
		hit.keyword_rank != null ? `keywords #${hit.keyword_rank}` : null,
		hit.rerank_score != null ? `rerank ${hit.rerank_score.toFixed(2)}` : null,
	]
		.filter(Boolean)
		.join(' · ');

export const FindTab = ({
	ontologyId,
	onOpen,
}: {
	ontologyId: string;
	onOpen: (iri: string) => void;
}) => {
	const [mode, setMode] = useState(Mode.Candidates);
	const [text, setText] = useState('');
	const [filter, setFilter] = useState(KindFilter.All);
	const [judge, setJudge] = useState(true);
	const search = useRequest<SearchResponse>();
	const candidates = useRequest<CandidatesResponse>();

	const submit = () => {
		const value = text.trim();
		if (!value) return;
		if (mode === Mode.Search) {
			void search.run(() => ontologiesApi.search(ontologyId, value, filter));
		} else {
			void candidates.run(() => ontologiesApi.candidates(ontologyId, value, filter, judge));
		}
	};

	const active = mode === Mode.Search ? search : candidates;

	return (
		<div className="flex flex-col gap-5 p-6">
			<Panel
				title="Find suitable concepts"
				description={
					mode === Mode.Candidates
						? 'Describe what you are looking for. Matching elements are retrieved, then the language model judges how each relates to your description.'
						: 'Hybrid search: meaning (embeddings) and keywords, fused and reranked.'
				}
				actions={
					<div
						role="radiogroup"
						aria-label="Mode"
						className="inline-flex rounded-lg border border-slate-200 p-0.5 dark:border-slate-700"
					>
						{[
							{ id: Mode.Candidates, label: 'Judged candidates' },
							{ id: Mode.Search, label: 'Search' },
						].map((m) => (
							<button
								key={m.id}
								type="button"
								role="radio"
								aria-checked={mode === m.id}
								onClick={() => setMode(m.id)}
								className={`cursor-pointer rounded-md px-2.5 py-1 text-xs transition-colors ${
									mode === m.id
										? 'bg-brand/10 font-medium text-brand-strong dark:bg-brand/20 dark:text-brand-light'
										: 'text-secondary hover:text-body dark:text-slate-400'
								}`}
							>
								{m.label}
							</button>
						))}
					</div>
				}
			>
				<form
					className="flex flex-col gap-3 sm:flex-row"
					onSubmit={(e) => {
						e.preventDefault();
						submit();
					}}
				>
					<input
						className={inputClass}
						placeholder={
							mode === Mode.Candidates
								? 'e.g. a small vessel to drink hot tea from'
								: 'e.g. cutting tool'
						}
						aria-label="Description"
						value={text}
						onChange={(e) => setText(e.target.value)}
					/>
					<KindSelect value={filter} onChange={setFilter} />
					<Button type="submit" loading={active.loading} disabled={!text.trim()}>
						{mode === Mode.Candidates ? 'Find' : 'Search'}
					</Button>
				</form>
				{mode === Mode.Candidates && (
					<div className="mt-3">
						<ToggleField
							label="Judge with the language model"
							checked={judge}
							onChange={setJudge}
						/>
					</div>
				)}
			</Panel>

			<ErrorNote message={active.error} />

			{mode === Mode.Candidates && candidates.data && (
				<Panel
					title={
						candidates.data.judged
							? candidates.data.suitable_exists
								? 'A suitable concept exists'
								: 'No exact match'
							: 'Closest elements'
					}
					description={candidates.data.summary || undefined}
				>
					{candidates.data.warnings.map((w) => (
						<div key={w} className="mb-3">
							<InfoNote>{w}</InfoNote>
						</div>
					))}
					{candidates.data.candidates.length === 0 ? (
						<p className="text-sm text-secondary dark:text-slate-400">Nothing fits.</p>
					) : (
						<ul className="divide-y divide-slate-100 dark:divide-slate-800">
							{candidates.data.candidates.map((c) => (
								<li key={c.iri} className="flex flex-col gap-1 py-3">
									<div className="flex flex-wrap items-center gap-2">
										{c.relation && <RelationBadge relation={c.relation} />}
										<ResultName iri={c.iri} name={c.name} onOpen={onOpen} />
										<KindBadge kind={c.kind} />
										{c.confidence != null && (
											<span className="text-[11px] text-secondary tabular-nums dark:text-slate-500">
												{Math.round(c.confidence * 100)}% sure
											</span>
										)}
									</div>
									<Path path={c.path} />
									{c.reason && (
										<p className="text-xs text-body dark:text-slate-300">
											{c.reason}
										</p>
									)}
									{!c.reason && c.definition && (
										<p className="text-xs text-secondary dark:text-slate-400">
											{c.definition}
										</p>
									)}
								</li>
							))}
						</ul>
					)}
				</Panel>
			)}

			{mode === Mode.Search && search.data && (
				<Panel
					title={`${search.data.results.length} results`}
					description={[
						search.data.dense
							? 'Meaning + keywords'
							: 'Keywords only (no embedding model)',
						search.data.reranker !== 'none'
							? `reranked (${search.data.reranker})`
							: 'not reranked',
					].join(' · ')}
				>
					<ul className="divide-y divide-slate-100 dark:divide-slate-800">
						{search.data.results.map((hit) => (
							<li key={hit.iri} className="flex flex-col gap-1 py-3">
								<div className="flex flex-wrap items-center gap-2">
									<ResultName iri={hit.iri} name={hit.name} onOpen={onOpen} />
									<KindBadge kind={hit.kind} />
									<span className="text-[11px] text-secondary dark:text-slate-500">
										{signals(hit)}
									</span>
								</div>
								<Path path={hit.path} />
								{hit.definition && (
									<p className="text-xs text-secondary dark:text-slate-400">
										{hit.definition}
									</p>
								)}
							</li>
						))}
					</ul>
				</Panel>
			)}
		</div>
	);
};
