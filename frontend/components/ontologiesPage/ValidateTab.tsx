// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useState } from 'react';

import { ontologiesApi } from '@/api/ontologies';
import { Button } from '@/common/Button';
import { FileUpload } from '@/common/FileUpload';
import { ButtonTheme } from '@/enums/button';
import type {
	DerivedShapesResponse,
	RulesShapesResponse,
	ValidationResponse,
} from '@/types/ontologies';

import { useRequest } from './hooks';
import {
	CodeBlock,
	Disclosure,
	ErrorNote,
	Field,
	InfoNote,
	Panel,
	StatTile,
	ToggleField,
	monoClass,
} from './ui';

export const ValidateTab = ({
	ontologyId,
	onOpen,
}: {
	ontologyId: string;
	onOpen: (iri: string) => void;
}) => {
	const derived = useRequest<DerivedShapesResponse>();
	const [rulesText, setRulesText] = useState('');
	const rules = useRequest<RulesShapesResponse>();
	const [data, setData] = useState('');
	const [file, setFile] = useState<File | null>(null);
	const [shapes, setShapes] = useState('');
	const [useDerived, setUseDerived] = useState(true);
	const [explain, setExplain] = useState(false);
	const validation = useRequest<ValidationResponse>();
	const v = validation.data;

	return (
		<div className="flex flex-col gap-5 p-6">
			<div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
				<Panel
					title="Rules from the ontology"
					description="Domains, ranges, functional properties, restrictions and disjointness, read as closed-world SHACL checks."
				>
					<div className="flex flex-col gap-3">
						<div>
							<Button
								theme={ButtonTheme.Secondary}
								loading={derived.loading}
								onClick={() =>
									void derived.run(() => ontologiesApi.derivedShapes(ontologyId))
								}
							>
								Show derived rules
							</Button>
						</div>
						<ErrorNote message={derived.error} />
						{derived.data && (
							<>
								<ul className="flex max-h-64 list-disc flex-col gap-1 overflow-y-auto pl-4 text-xs text-body dark:text-slate-300">
									{derived.data.rules.map((r, i) => (
										<li key={i}>{r}</li>
									))}
								</ul>
								<Disclosure summary="As SHACL">
									<CodeBlock code={derived.data.turtle} label="SHACL (Turtle)" />
								</Disclosure>
							</>
						)}
					</div>
				</Panel>

				<Panel
					title="Rules in plain language"
					description="One rule per line. The language model writes SHACL for them using this ontology's terms."
				>
					<div className="flex flex-col gap-3">
						<textarea
							className={`${monoClass} min-h-24 font-sans text-sm`}
							aria-label="Rules, one per line"
							placeholder={
								'Every robot must be located somewhere\nA knife weighs at most 500 g'
							}
							value={rulesText}
							onChange={(e) => setRulesText(e.target.value)}
						/>
						<div>
							<Button
								loading={rules.loading}
								disabled={!rulesText.trim()}
								onClick={() =>
									void rules.run(() =>
										ontologiesApi.shapesFromRules(
											ontologyId,
											rulesText
												.split('\n')
												.map((r) => r.trim())
												.filter(Boolean),
										),
									)
								}
							>
								Write SHACL
							</Button>
						</div>
						<ErrorNote message={rules.error} />
						{rules.data && (
							<>
								{!rules.data.ok && (
									<ErrorNote message={rules.data.problems.join(' ')} />
								)}
								{rules.data.notes.map((n) => (
									<InfoNote key={n}>{n}</InfoNote>
								))}
								<CodeBlock
									code={rules.data.turtle}
									label="SHACL (Turtle)"
									onApply={() => setShapes(rules.data!.turtle)}
									applyLabel="Use for validation"
								/>
							</>
						)}
					</div>
				</Panel>
			</div>

			<Panel
				title="Validate data"
				description="Paste RDF or upload a file. Leave it empty to check the ontology's own individuals."
			>
				<form
					className="flex flex-col gap-4"
					onSubmit={(e) => {
						e.preventDefault();
						void validation.run(() =>
							ontologiesApi.validate(ontologyId, {
								data,
								shapes,
								use_derived: useDerived,
								explain,
							}),
						);
					}}
				>
					<div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
						<Field label="Data (Turtle, RDF/XML, N-Triples, JSON-LD)">
							<textarea
								className={`${monoClass} min-h-40`}
								spellCheck={false}
								value={data}
								onChange={(e) => setData(e.target.value)}
								placeholder="@prefix : <http://example.org/kitchen#> .&#10;:r1 a :Robot ."
							/>
						</Field>
						<Field label="Extra shapes (SHACL Turtle, optional)">
							<textarea
								className={`${monoClass} min-h-40`}
								spellCheck={false}
								value={shapes}
								onChange={(e) => setShapes(e.target.value)}
							/>
						</Field>
					</div>
					<FileUpload
						value={file}
						onChange={async (f) => {
							setFile(f);
							if (f) setData(await f.text());
						}}
						accept=".ttl,.rdf,.owl,.xml,.nt,.jsonld,.json,.n3"
						label="Or upload a data file"
						description="Its contents replace the data above."
					/>
					<div className="flex flex-wrap items-center justify-between gap-3">
						<div className="flex flex-wrap gap-4">
							<ToggleField
								label="Apply rules from the ontology"
								checked={useDerived}
								onChange={setUseDerived}
							/>
							<ToggleField
								label="Explain the results"
								checked={explain}
								onChange={setExplain}
							/>
						</div>
						<Button type="submit" loading={validation.loading}>
							Validate
						</Button>
					</div>
				</form>
			</Panel>

			<ErrorNote message={validation.error} />

			{v && (
				<Panel
					title={v.conforms ? 'The data conforms' : 'The data has problems'}
					description={`Checked ${v.source}.`}
				>
					<div className="flex flex-col gap-4">
						<div className="grid grid-cols-3 gap-3 sm:max-w-md">
							<StatTile
								label="Conforms"
								value={v.conforms ? 'Yes' : 'No'}
								tone={v.conforms ? 'good' : 'bad'}
							/>
							<StatTile
								label="Violations"
								value={v.violations}
								tone={v.violations ? 'bad' : 'neutral'}
							/>
							<StatTile label="Warnings" value={v.warnings} />
						</div>
						{v.explanation && (
							<p className="text-sm leading-relaxed whitespace-pre-wrap text-body dark:text-slate-300">
								{v.explanation}
							</p>
						)}
						{v.results.length > 0 && (
							<div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
								<table className="w-full text-left text-xs">
									<thead className="bg-slate-50 text-secondary dark:bg-slate-800/60 dark:text-slate-400">
										<tr>
											<th className="px-3 py-2 font-medium">Severity</th>
											<th className="px-3 py-2 font-medium">Node</th>
											<th className="px-3 py-2 font-medium">Property</th>
											<th className="px-3 py-2 font-medium">Value</th>
											<th className="px-3 py-2 font-medium">Problem</th>
										</tr>
									</thead>
									<tbody className="divide-y divide-slate-100 dark:divide-slate-800">
										{v.results.map((r, i) => (
											<tr key={i}>
												<td
													className={`px-3 py-1.5 font-medium ${
														r.severity === 'Violation'
															? 'text-red-700 dark:text-red-300'
															: 'text-amber-700 dark:text-amber-300'
													}`}
												>
													{r.severity}
												</td>
												<td
													className="px-3 py-1.5 text-body dark:text-slate-300"
													title={r.focus_node ?? ''}
												>
													{/* Only the ontology's own individuals can be opened. */}
													{r.focus_node &&
													v.source !== 'uploaded data' ? (
														<button
															type="button"
															className="cursor-pointer hover:underline"
															onClick={() => onOpen(r.focus_node!)}
														>
															{r.focus_name}
														</button>
													) : (
														(r.focus_name ?? '—')
													)}
												</td>
												<td className="px-3 py-1.5 text-body dark:text-slate-300">
													{r.path_name ?? '—'}
												</td>
												<td className="px-3 py-1.5 font-mono text-body dark:text-slate-300">
													{r.value ?? ''}
												</td>
												<td className="px-3 py-1.5 text-secondary dark:text-slate-400">
													{r.message}
												</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
						)}
					</div>
				</Panel>
			)}
		</div>
	);
};
