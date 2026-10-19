// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useState } from 'react';

import { ontologiesApi } from '@/api/ontologies';
import { Button } from '@/common/Button';
import { ButtonTheme, Size } from '@/enums/button';
import { KindFilter } from '@/enums/ontologies';
import type {
	ChildrenResponse,
	DefinitionsResponse,
	IssuesResponse,
	OntoRef,
	PlacementResponse,
} from '@/types/ontologies';

import { useAddTriples, useRequest, type Notify } from './hooks';
import {
	CodeBlock,
	Disclosure,
	ElementPicker,
	ErrorNote,
	Field,
	InfoNote,
	Panel,
	RefChip,
	RefList,
	ToggleField,
	inputClass,
} from './ui';

type Props = { ontologyId: string; onOpen: (iri: string) => void; notify: Notify };

const Placement = ({ ontologyId, onOpen, notify }: Props) => {
	const [name, setName] = useState('');
	const [description, setDescription] = useState('');
	const req = useRequest<PlacementResponse>();
	const { apply, applying } = useAddTriples(ontologyId, notify);
	const p = req.data;
	return (
		<Panel
			title="Place a new concept"
			description="Where does it belong — or does the ontology already have it?"
		>
			<form
				className="flex flex-col gap-3"
				onSubmit={(e) => {
					e.preventDefault();
					if (name.trim())
						void req.run(() =>
							ontologiesApi.placement(ontologyId, name.trim(), description.trim()),
						);
				}}
			>
				<Field label="Name">
					<input
						className={inputClass}
						value={name}
						onChange={(e) => setName(e.target.value)}
						placeholder="e.g. Spatula"
					/>
				</Field>
				<Field label="Description (optional)">
					<input
						className={inputClass}
						value={description}
						onChange={(e) => setDescription(e.target.value)}
						placeholder="e.g. a flat tool for flipping pancakes"
					/>
				</Field>
				<div>
					<Button type="submit" loading={req.loading} disabled={!name.trim()}>
						Suggest placement
					</Button>
				</div>
			</form>
			<div className="mt-4 flex flex-col gap-3">
				<ErrorNote message={req.error} />
				{p?.existing_equivalent && (
					<InfoNote>
						Already in the ontology as{' '}
						<button
							type="button"
							className="cursor-pointer font-medium underline"
							onClick={() => onOpen(p.existing_equivalent!.iri)}
						>
							{p.existing_equivalent.name}
						</button>
						. {p.existing_equivalent.reason}
					</InfoNote>
				)}
				{p && !p.existing_equivalent && (
					<>
						<div className="flex flex-col gap-2">
							{p.parents.map((parent) => (
								<div key={parent.iri} className="flex flex-col gap-0.5">
									<div className="flex items-center gap-2 text-xs text-secondary dark:text-slate-400">
										<span>A kind of</span>
										<RefChip value={parent} onOpen={onOpen} />
										<span className="text-[11px]">
											({[...parent.path].reverse().join(' › ')})
										</span>
									</div>
									<p className="text-xs text-body dark:text-slate-300">
										{parent.reason}
									</p>
								</div>
							))}
							{p.parents.length === 0 && (
								<InfoNote>
									No suitable parent was found; it would be a top-level class.
								</InfoNote>
							)}
						</div>
						<p className="text-sm text-body dark:text-slate-300">
							<span className="font-medium text-heading dark:text-slate-100">
								{p.label}:
							</span>{' '}
							{p.definition}
						</p>
						{p.suggested_restrictions.length > 0 && (
							<div className="text-xs text-secondary dark:text-slate-400">
								Worth adding by hand:{' '}
								<span className="font-mono">
									{p.suggested_restrictions.join('; ')}
								</span>
							</div>
						)}
						<CodeBlock
							code={p.turtle}
							label="Turtle"
							onApply={() => void apply(p.turtle, 'placement')}
							applying={applying === 'placement'}
						/>
					</>
				)}
			</div>
		</Panel>
	);
};

const Children = ({ ontologyId, onOpen, notify }: Props) => {
	const [target, setTarget] = useState<OntoRef | null>(null);
	const req = useRequest<ChildrenResponse>();
	const { apply, applying } = useAddTriples(ontologyId, notify);
	return (
		<Panel
			title="Suggest missing subclasses"
			description="Subclasses a class probably needs, judged against its existing children and siblings."
		>
			<div className="flex flex-col gap-3">
				<ElementPicker
					ontologyId={ontologyId}
					filter={KindFilter.Class}
					value={target}
					onChange={setTarget}
					placeholder="Type a class name"
				/>
				<div>
					<Button
						disabled={!target}
						loading={req.loading}
						onClick={() =>
							target &&
							void req.run(() => ontologiesApi.children(ontologyId, target.iri))
						}
					>
						Suggest
					</Button>
				</div>
				<ErrorNote message={req.error} />
				{req.data?.suggestions.length === 0 && (
					<InfoNote>Nothing obvious is missing under {req.data.name}.</InfoNote>
				)}
				{req.data?.suggestions.map((s) => (
					<div
						key={s.proposed_iri}
						className="flex flex-col gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700"
					>
						<div className="flex items-start justify-between gap-2">
							<div>
								<p className="text-sm font-medium text-heading dark:text-slate-100">
									{s.label}
								</p>
								<p className="text-xs text-body dark:text-slate-300">
									{s.definition}
								</p>
								<p className="mt-1 text-[11px] text-secondary dark:text-slate-500">
									{s.reason}
								</p>
							</div>
							<Button
								size={Size.SMALL}
								theme={ButtonTheme.Soft}
								loading={applying === s.proposed_iri}
								onClick={() => void apply(s.turtle, s.proposed_iri)}
							>
								Add
							</Button>
						</div>
						{s.possibly_existing.length > 0 && (
							<div className="flex items-center gap-2 text-[11px] text-amber-700 dark:text-amber-300">
								Might already exist as{' '}
								<RefList values={s.possibly_existing} onOpen={onOpen} />
							</div>
						)}
					</div>
				))}
			</div>
		</Panel>
	);
};

const Definitions = ({ ontologyId, onOpen, notify }: Props) => {
	const req = useRequest<DefinitionsResponse>();
	const { apply, applying } = useAddTriples(ontologyId, notify);
	const drafts = req.data?.definitions ?? [];
	return (
		<Panel
			title="Draft definitions"
			description="Genus-differentia definitions for classes that have none, grounded in their axioms."
			actions={
				drafts.length > 1 ? (
					<Button
						size={Size.SMALL}
						theme={ButtonTheme.Soft}
						loading={applying === 'all'}
						onClick={() => void apply(drafts.map((d) => d.turtle).join(''), 'all')}
					>
						Add all
					</Button>
				) : undefined
			}
		>
			<div className="flex flex-col gap-3">
				<div>
					<Button
						loading={req.loading}
						onClick={() => void req.run(() => ontologiesApi.definitions(ontologyId))}
					>
						Draft up to 20
					</Button>
				</div>
				<ErrorNote message={req.error} />
				{req.data && drafts.length === 0 && (
					<InfoNote>Every class already has a definition.</InfoNote>
				)}
				<ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
					{drafts.map((d) => (
						<li key={d.iri} className="flex items-start justify-between gap-3 py-2.5">
							<div className="min-w-0">
								<RefChip value={d} onOpen={onOpen} />
								<p className="mt-1 text-xs text-body dark:text-slate-300">
									{d.definition}
								</p>
							</div>
							<Button
								size={Size.SMALL}
								theme={ButtonTheme.Soft}
								loading={applying === d.iri}
								onClick={() => void apply(d.turtle, d.iri)}
							>
								Add
							</Button>
						</li>
					))}
				</ul>
			</div>
		</Panel>
	);
};

const IssueGroup = ({
	title,
	values,
	onOpen,
}: {
	title: string;
	values: OntoRef[];
	onOpen: (iri: string) => void;
}) =>
	values.length === 0 ? null : (
		<Disclosure summary={`${title} (${values.length})`}>
			<RefList values={values.slice(0, 200)} onOpen={onOpen} />
		</Disclosure>
	);

const VERDICT_TEXT: Record<string, string> = {
	same: 'Same concept',
	one_is_kind_of_other: 'One is a kind of the other',
	distinct: 'Distinct',
};

const Issues = ({ ontologyId, onOpen }: Props) => {
	const [review, setReview] = useState(false);
	const req = useRequest<IssuesResponse>();
	const r = req.data;
	return (
		<Panel
			title="Check for issues"
			description="Possible duplicates, gaps and structural problems. The checks are deterministic; the optional review asks the language model about each duplicate pair."
		>
			<div className="flex flex-col gap-3">
				<div className="flex flex-wrap items-center gap-4">
					<Button
						loading={req.loading}
						onClick={() => void req.run(() => ontologiesApi.issues(ontologyId, review))}
					>
						Check
					</Button>
					<ToggleField
						label="Review duplicates with the model"
						checked={review}
						onChange={setReview}
					/>
				</div>
				<ErrorNote message={req.error} />
				{r?.warnings.map((w) => (
					<InfoNote key={w}>{w}</InfoNote>
				))}
				{r && (
					<>
						{r.duplicates.length > 0 && (
							<Disclosure summary={`Possible duplicates (${r.duplicates.length})`}>
								<ul className="flex flex-col gap-2">
									{r.duplicates.map((d) => (
										<li
											key={`${d.a.iri}|${d.b.iri}`}
											className="flex flex-col gap-1 text-xs text-secondary dark:text-slate-400"
										>
											<div className="flex flex-wrap items-center gap-1.5">
												<RefChip value={d.a} onOpen={onOpen} />
												<span>and</span>
												<RefChip value={d.b} onOpen={onOpen} />
												<span>· {d.relation}</span>
												<span>· {d.evidence.join(', ')}</span>
												{d.verdict && (
													<span className="font-medium text-body dark:text-slate-300">
														· {VERDICT_TEXT[d.verdict] ?? d.verdict}
													</span>
												)}
											</div>
											{d.reason && <p>{d.reason}</p>}
										</li>
									))}
								</ul>
							</Disclosure>
						)}
						<IssueGroup
							title="Classes without a definition"
							values={r.missing_definitions}
							onOpen={onOpen}
						/>
						<IssueGroup
							title="Classes without a label"
							values={r.missing_labels}
							onOpen={onOpen}
						/>
						<IssueGroup
							title="Top-level classes"
							values={r.root_classes}
							onOpen={onOpen}
						/>
						<IssueGroup
							title="Classes with a single subclass"
							values={r.single_child_classes}
							onOpen={onOpen}
						/>
						<IssueGroup
							title="Properties without a domain"
							values={r.properties_without_domain}
							onOpen={onOpen}
						/>
						<IssueGroup
							title="Properties without a range"
							values={r.properties_without_range}
							onOpen={onOpen}
						/>
						<IssueGroup
							title="Hierarchy cycles"
							values={r.hierarchy_cycles}
							onOpen={onOpen}
						/>
						<IssueGroup
							title="Deprecated classes still used as parents"
							values={r.deprecated_parents}
							onOpen={onOpen}
						/>
					</>
				)}
			</div>
		</Panel>
	);
};

export const GrowTab = (props: Props) => (
	<div className="grid grid-cols-1 gap-5 p-6 xl:grid-cols-2">
		<Placement {...props} />
		<Children {...props} />
		<Definitions {...props} />
		<Issues {...props} />
	</div>
);
