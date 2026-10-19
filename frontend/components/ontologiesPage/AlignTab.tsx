// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useState } from 'react';

import { ontologiesApi } from '@/api/ontologies';
import { Button } from '@/common/Button';
import { ButtonTheme } from '@/enums/button';
import type { AlignResponse, OntologySummary } from '@/types/ontologies';

import { useAddTriples, type Notify } from './hooks';
import {
	ErrorNote,
	Field,
	InfoNote,
	Panel,
	RefChip,
	RelationBadge,
	ToggleField,
	downloadText,
	selectClass,
} from './ui';

const BATCH = 50;

/** The batches so far, merged: mappings and unmatched elements accumulate. */
const merge = (prev: AlignResponse | null, next: AlignResponse): AlignResponse =>
	prev == null || next.offset === 0
		? next
		: {
				...next,
				mappings: [...prev.mappings, ...next.mappings],
				unmatched: [...prev.unmatched, ...next.unmatched],
				warnings: Array.from(new Set([...prev.warnings, ...next.warnings])),
				sssom_tsv:
					prev.sssom_tsv +
					next.sssom_tsv
						.split('\n')
						.filter(
							(line) =>
								line && !line.startsWith('#') && !line.startsWith('subject_id'),
						)
						.map((line) => `${line}\n`)
						.join(''),
				turtle:
					prev.turtle +
					next.turtle
						.split('\n')
						.filter((line) => line && !line.startsWith('@prefix'))
						.map((line) => `${line}\n`)
						.join(''),
				processed: prev.processed + next.processed,
			};

export const AlignTab = ({
	ontology,
	ontologies,
	onOpen,
	notify,
}: {
	ontology: OntologySummary;
	ontologies: OntologySummary[];
	onOpen: (iri: string) => void;
	notify: Notify;
}) => {
	const others = ontologies.filter((o) => o.id !== ontology.id);
	const [targetId, setTargetId] = useState(others[0]?.id ?? '');
	const [judge, setJudge] = useState(true);
	const [result, setResult] = useState<AlignResponse | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const { apply, applying } = useAddTriples(ontology.id, notify);

	const run = async (offset: number) => {
		setLoading(true);
		setError(null);
		const res = await ontologiesApi.align(ontology.id, targetId, judge, BATCH, offset);
		setLoading(false);
		if (res.error) {
			setError(res.message ?? 'Alignment failed.');
			return;
		}
		setResult((prev) => merge(prev, res));
	};

	if (others.length === 0) {
		return (
			<div className="p-6">
				<InfoNote>Load a second ontology to align this one with it.</InfoNote>
			</div>
		);
	}

	const targetTitle =
		ontologies.find((o) => o.id === (result?.target ?? targetId))?.title ?? targetId;

	return (
		<div className="flex flex-col gap-5 p-6">
			<Panel
				title="Align with another ontology"
				description={`Find which classes of ${ontology.title} match classes of another ontology. Candidates come from labels and meaning; the language model then judges each.`}
			>
				<form
					className="flex flex-col gap-3"
					onSubmit={(e) => {
						e.preventDefault();
						setResult(null);
						void run(0);
					}}
				>
					<div className="flex flex-wrap items-end gap-3">
						<Field label="Target ontology">
							<select
								className={`${selectClass} min-w-56`}
								value={targetId}
								onChange={(e) => setTargetId(e.target.value)}
							>
								{others.map((o) => (
									<option key={o.id} value={o.id}>
										{o.title}
									</option>
								))}
							</select>
						</Field>
						<Button type="submit" loading={loading && !result}>
							Align first {BATCH} classes
						</Button>
					</div>
					<ToggleField
						label="Judge with the language model (off: best label/meaning match only)"
						checked={judge}
						onChange={setJudge}
					/>
				</form>
			</Panel>

			<ErrorNote message={error} />

			{result && (
				<Panel
					title={`${result.mappings.length} mappings to ${targetTitle}`}
					description={`${result.processed} of ${result.total_sources} source classes processed · ${result.unmatched.length} without a match`}
					actions={
						<>
							<Button
								theme={ButtonTheme.Secondary}
								onClick={() =>
									downloadText(
										result.sssom_tsv,
										`${result.source}-${result.target}.sssom.tsv`,
									)
								}
							>
								SSSOM
							</Button>
							<Button
								theme={ButtonTheme.Secondary}
								onClick={() =>
									downloadText(
										result.turtle,
										`${result.source}-${result.target}.ttl`,
										'text/turtle',
									)
								}
							>
								Turtle
							</Button>
							<Button
								theme={ButtonTheme.Soft}
								disabled={result.mappings.length === 0}
								loading={applying === 'align'}
								onClick={() => void apply(result.turtle, 'align')}
							>
								Add to {ontology.title}
							</Button>
						</>
					}
				>
					{result.warnings.map((w) => (
						<div key={w} className="mb-3">
							<InfoNote>{w}</InfoNote>
						</div>
					))}
					{result.mappings.length > 0 && (
						<div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
							<table className="w-full text-left text-xs">
								<thead className="bg-slate-50 text-secondary dark:bg-slate-800/60 dark:text-slate-400">
									<tr>
										<th className="px-3 py-2 font-medium">{ontology.title}</th>
										<th className="px-3 py-2 font-medium">Target is</th>
										<th className="px-3 py-2 font-medium">{targetTitle}</th>
										<th className="px-3 py-2 font-medium">Confidence</th>
										<th className="px-3 py-2 font-medium">Why</th>
									</tr>
								</thead>
								<tbody className="divide-y divide-slate-100 dark:divide-slate-800">
									{result.mappings.map((m) => (
										<tr key={`${m.source.iri}|${m.target.iri}`}>
											<td className="px-3 py-1.5">
												<RefChip value={m.source} onOpen={onOpen} />
											</td>
											<td className="px-3 py-1.5">
												<RelationBadge relation={m.relation} />
											</td>
											<td className="px-3 py-1.5">
												<RefChip value={m.target} />
											</td>
											<td className="px-3 py-1.5 tabular-nums">
												{/* Unjudged matches by meaning carry a fusion score, not a confidence. */}
												{m.reason || m.label_match
													? `${Math.round(m.confidence * 100)}%`
													: '—'}
											</td>
											<td className="px-3 py-1.5 text-secondary dark:text-slate-400">
												{m.reason ||
													(m.label_match
														? 'Same label'
														: 'Closest by meaning')}
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
					)}
					{result.next_offset != null && (
						<div className="mt-3">
							<Button
								theme={ButtonTheme.Secondary}
								loading={loading}
								onClick={() => void run(result.next_offset!)}
							>
								Align the next {BATCH}
							</Button>
						</div>
					)}
				</Panel>
			)}
		</div>
	);
};
