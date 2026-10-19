// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useDeferredValue, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';

import { CopyButton } from '@/common/Button';
import { EmptyState } from '@/common/EmptyState';
import { SkeletonBlock } from '@/common/Skeleton';
import { EmptyStateVariant } from '@/enums/emptyState';
import { ElementKind, KindFilter } from '@/enums/ontologies';
import { ontologyQueries } from '@/lib/queries/ontologies';
import type { ElementDetail } from '@/types/ontologies';

import {
	Disclosure,
	ErrorNote,
	InfoNote,
	KindBadge,
	KindSelect,
	RefList,
	inputClass,
	reasonerName,
} from './ui';

const Row = ({ label, children }: { label: string; children: ReactNode }) => (
	<div className="grid grid-cols-[140px_1fr] gap-3 py-2">
		<dt className="text-xs font-medium text-secondary dark:text-slate-400">{label}</dt>
		<dd className="min-w-0 text-sm text-body dark:text-slate-300">{children}</dd>
	</div>
);

const TextList = ({ values }: { values: string[] }) => (
	<ul className="flex flex-col gap-1">
		{values.map((v) => (
			<li key={v} className="font-mono text-xs break-words">
				{v}
			</li>
		))}
	</ul>
);

const ElementDetailView = ({
	element,
	onOpen,
}: {
	element: ElementDetail;
	onOpen: (iri: string) => void;
}) => {
	const isClass = element.kind === ElementKind.Class;
	const isProperty =
		element.kind === ElementKind.ObjectProperty ||
		element.kind === ElementKind.DatatypeProperty ||
		element.kind === ElementKind.AnnotationProperty;
	const inferred = element.inferred;
	return (
		<article className="flex flex-col gap-4">
			<header className="flex flex-col gap-2">
				<div className="flex flex-wrap items-center gap-2">
					<h2 className="text-xl font-semibold tracking-tight text-heading dark:text-slate-100">
						{element.name}
					</h2>
					<KindBadge kind={element.kind} />
					{element.deprecated && (
						<span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
							Deprecated
						</span>
					)}
				</div>
				<div className="flex min-w-0 items-center gap-1">
					<code
						className="truncate text-xs text-secondary dark:text-slate-400"
						title={element.iri}
					>
						{element.iri}
					</code>
					<CopyButton text={element.iri} />
				</div>
				{element.path.length > 1 && (
					<p className="text-xs text-secondary dark:text-slate-400">
						{[...element.path].reverse().join(' › ')}
					</p>
				)}
			</header>

			{(element.definition || element.comment) && (
				<p className="max-w-3xl text-sm leading-relaxed text-body dark:text-slate-300">
					{element.definition || element.comment}
				</p>
			)}

			{inferred?.unsatisfiable && (
				<ErrorNote
					message={`${reasonerName(inferred.backend)} found this class unsatisfiable: nothing can be a member of it.`}
				/>
			)}

			<dl className="divide-y divide-slate-100 dark:divide-slate-800">
				{element.alt_labels.length > 0 && (
					<Row label="Also called">{element.alt_labels.join(', ')}</Row>
				)}
				{isClass && (
					<>
						<Row label="Parents">
							<RefList
								values={element.parents}
								onOpen={onOpen}
								empty="Top-level class"
							/>
						</Row>
						<Row label="Subclasses">
							<RefList values={element.children} onOpen={onOpen} empty="None" />
						</Row>
						{element.equivalents.length > 0 && (
							<Row label="Equivalent to">
								<TextList values={element.equivalents.map((e) => e.name)} />
							</Row>
						)}
						{element.restrictions.length > 0 && (
							<Row label="Restrictions">
								<TextList values={element.restrictions} />
							</Row>
						)}
						{element.disjoint_with.length > 0 && (
							<Row label="Disjoint with">
								<RefList values={element.disjoint_with} onOpen={onOpen} />
							</Row>
						)}
					</>
				)}
				{isProperty && (
					<>
						<Row label="Subproperty of">
							<RefList values={element.parents} onOpen={onOpen} empty="None" />
						</Row>
						<Row label="Domain">
							<RefList values={element.domain} onOpen={onOpen} empty="Not stated" />
						</Row>
						<Row label="Range">
							<RefList values={element.range} onOpen={onOpen} empty="Not stated" />
						</Row>
						{element.inverse_of.length > 0 && (
							<Row label="Inverse of">
								<RefList values={element.inverse_of} onOpen={onOpen} />
							</Row>
						)}
						{element.characteristics.length > 0 && (
							<Row label="Characteristics">{element.characteristics.join(', ')}</Row>
						)}
					</>
				)}
				{element.kind === ElementKind.Individual && (
					<>
						<Row label="Instance of">
							<RefList
								values={element.types}
								onOpen={onOpen}
								empty="No stated class"
							/>
						</Row>
						{element.assertions.length > 0 && (
							<Row label="Facts">
								<ul className="flex flex-col gap-1">
									{element.assertions.map((a, i) => (
										<li key={i} className="text-sm">
											<span className="text-secondary dark:text-slate-400">
												{a.property_name}
											</span>{' '}
											{a.value}
										</li>
									))}
								</ul>
							</Row>
						)}
					</>
				)}
				{inferred && !inferred.unsatisfiable && (
					<>
						{isClass && (
							<Row label={`Inferred parents`}>
								<RefList
									values={inferred.superclasses}
									onOpen={onOpen}
									empty="Nothing beyond what is stated"
								/>
							</Row>
						)}
						{element.kind === ElementKind.Individual && (
							<Row label="Inferred classes">
								<RefList
									values={inferred.types}
									onOpen={onOpen}
									empty="Nothing beyond what is stated"
								/>
							</Row>
						)}
					</>
				)}
			</dl>

			{!inferred && (isClass || element.kind === ElementKind.Individual) && (
				<InfoNote>
					Run a reasoner (Reason tab) to see inferred parents and classes here.
				</InfoNote>
			)}

			<Disclosure summary="Indexed text (what search and the language model see)">
				<pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap text-body dark:text-slate-300">
					{element.document}
				</pre>
			</Disclosure>
		</article>
	);
};

export const ExploreTab = ({
	ontologyId,
	iri,
	onOpen,
}: {
	ontologyId: string;
	iri: string | null;
	onOpen: (iri: string) => void;
}) => {
	const [filter, setFilter] = useState<KindFilter>(KindFilter.Class);
	const [text, setText] = useState('');
	const q = useDeferredValue(text.trim());
	const list = useQuery(ontologyQueries.elements(ontologyId, filter, q));
	const detail = useQuery({
		...ontologyQueries.element(ontologyId, iri ?? ''),
		enabled: iri != null,
	});

	return (
		<div className="grid grid-cols-1 lg:min-h-0 lg:flex-1 lg:grid-cols-[320px_1fr]">
			<aside className="flex min-h-0 flex-col border-b border-slate-200 lg:border-r lg:border-b-0 dark:border-slate-800">
				<div className="flex gap-2 p-3">
					<input
						className={inputClass}
						placeholder="Filter by name"
						aria-label="Filter elements by name"
						value={text}
						onChange={(e) => setText(e.target.value)}
					/>
					<KindSelect value={filter} onChange={setFilter} />
				</div>
				<div className="px-3 pb-2 text-[11px] text-secondary dark:text-slate-500">
					{list.data
						? `${list.data.total} element${list.data.total === 1 ? '' : 's'}${
								list.data.total > list.data.elements.length
									? `, first ${list.data.elements.length} shown`
									: ''
							}`
						: ' '}
				</div>
				<ul className="max-h-72 overflow-y-auto px-2 pb-3 lg:max-h-none lg:min-h-0 lg:flex-1">
					{list.isPending &&
						Array.from({ length: 8 }).map((_, i) => (
							<li key={i} className="px-2 py-1.5">
								<SkeletonBlock className="h-5 w-full" />
							</li>
						))}
					{list.data?.elements.map((e) => (
						<li key={e.iri}>
							<button
								type="button"
								onClick={() => onOpen(e.iri)}
								title={e.definition || e.iri}
								className={`flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors ${
									e.iri === iri
										? 'bg-brand/10 font-medium text-heading dark:bg-brand/20 dark:text-slate-100'
										: 'text-body hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800/60'
								}`}
							>
								<span className="truncate">{e.name}</span>
								{filter !== KindFilter.Class && <KindBadge kind={e.kind} />}
							</button>
						</li>
					))}
				</ul>
			</aside>
			<section className="min-w-0 p-6 lg:overflow-y-auto">
				{iri == null ? (
					<EmptyState
						variant={EmptyStateVariant.Borderless}
						title="Pick an element"
						description="Choose a class, property or individual on the left to see its definition, hierarchy, axioms and anything a reasoner inferred about it."
					/>
				) : detail.isPending ? (
					<div className="flex flex-col gap-3">
						<SkeletonBlock className="h-7 w-64" />
						<SkeletonBlock className="h-4 w-96" />
						<SkeletonBlock className="h-24 w-full" />
					</div>
				) : detail.error ? (
					<ErrorNote message={detail.error.message} />
				) : (
					detail.data && <ElementDetailView element={detail.data} onOpen={onOpen} />
				)}
			</section>
		</div>
	);
};
