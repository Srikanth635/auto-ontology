// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';

import { Button, CopyButton } from '@/common/Button';
import { Toggle } from '@/common/Toggle';
import { ButtonTheme, Size } from '@/enums/button';
import { CandidateRelation, ElementKind, KindFilter, ReasonerBackend } from '@/enums/ontologies';
import { ontologyQueries } from '@/lib/queries/ontologies';
import type { OntoRef, ReasonersResponse, SparqlResult, SparqlTerm } from '@/types/ontologies';

export const inputClass =
	'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-body outline-none transition-colors placeholder:text-secondary focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:placeholder:text-slate-500';

/** For selects, which size to their content instead of filling the row. */
export const selectClass =
	'w-auto rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-body outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200';

export const monoClass =
	'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-body outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200';

/** How a reasoner backend is written for people. */
export const reasonerName = (backend: string): string =>
	backend === 'hermit' ? 'HermiT' : backend === 'owlrl' ? 'OWL RL' : backend;

/** A titled card that holds one tool of the workspace. */
export const Panel = ({
	title,
	description,
	actions,
	children,
}: {
	title?: ReactNode;
	description?: ReactNode;
	actions?: ReactNode;
	children: ReactNode;
}) => (
	<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
		{(title || actions) && (
			<header className="mb-4 flex items-start justify-between gap-3">
				<div className="min-w-0">
					{title && (
						<h2 className="text-sm font-semibold text-heading dark:text-slate-100">
							{title}
						</h2>
					)}
					{description && (
						<p className="mt-1 text-xs text-secondary dark:text-slate-400">
							{description}
						</p>
					)}
				</div>
				{actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
			</header>
		)}
		{children}
	</section>
);

export const Field = ({ label, children }: { label: string; children: ReactNode }) => (
	<label className="flex flex-col gap-1.5">
		<span className="text-xs font-medium text-secondary dark:text-slate-400">{label}</span>
		{children}
	</label>
);

export const ErrorNote = ({ message }: { message: string | null | undefined }) =>
	message ? (
		<p
			role="alert"
			className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300"
		>
			{message}
		</p>
	) : null;

export const InfoNote = ({ children }: { children: ReactNode }) => (
	<p className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-300">
		{children}
	</p>
);

const KIND_LABEL: Record<ElementKind, string> = {
	[ElementKind.Class]: 'Class',
	[ElementKind.ObjectProperty]: 'Object property',
	[ElementKind.DatatypeProperty]: 'Data property',
	[ElementKind.AnnotationProperty]: 'Annotation',
	[ElementKind.Individual]: 'Individual',
};

const KIND_CLASS: Record<ElementKind, string> = {
	[ElementKind.Class]: 'bg-brand/10 text-brand-strong dark:text-brand-light',
	[ElementKind.ObjectProperty]:
		'bg-violet-100 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300',
	[ElementKind.DatatypeProperty]:
		'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300',
	[ElementKind.AnnotationProperty]:
		'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
	[ElementKind.Individual]: 'bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300',
};

export const KindBadge = ({ kind }: { kind: ElementKind }) => (
	<span
		className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ${KIND_CLASS[kind]}`}
	>
		{KIND_LABEL[kind]}
	</span>
);

const RELATION_CLASS: Record<string, string> = {
	[CandidateRelation.Exact]:
		'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300',
	equivalent: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300',
	[CandidateRelation.Narrower]: 'bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300',
	[CandidateRelation.Broader]:
		'bg-violet-100 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300',
	[CandidateRelation.Related]:
		'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
	[CandidateRelation.Unrelated]:
		'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
};

export const RelationBadge = ({ relation }: { relation: string }) => (
	<span
		className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium capitalize ${
			RELATION_CLASS[relation] ?? RELATION_CLASS[CandidateRelation.Related]
		}`}
	>
		{relation}
	</span>
);

/** An element reference that opens the element in Explore. */
export const RefChip = ({ value, onOpen }: { value: OntoRef; onOpen?: (iri: string) => void }) =>
	onOpen ? (
		<button
			type="button"
			onClick={() => onOpen(value.iri)}
			title={value.iri}
			className="inline-flex max-w-full cursor-pointer items-center truncate rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs text-body transition-colors hover:border-brand hover:text-brand-strong dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:text-brand-light"
		>
			{value.name}
		</button>
	) : (
		<span
			title={value.iri}
			className="inline-flex max-w-full items-center truncate rounded-md border border-slate-200 px-2 py-0.5 text-xs text-body dark:border-slate-700 dark:text-slate-300"
		>
			{value.name}
		</span>
	);

export const KindSelect = ({
	value,
	onChange,
	withIndividuals = true,
}: {
	value: KindFilter;
	onChange: (value: KindFilter) => void;
	withIndividuals?: boolean;
}) => (
	<select
		aria-label="Element kind"
		value={value}
		onChange={(e) => onChange(e.target.value as KindFilter)}
		className={selectClass}
	>
		<option value={KindFilter.All}>All kinds</option>
		<option value={KindFilter.Class}>Classes</option>
		<option value={KindFilter.Property}>Properties</option>
		{withIndividuals && <option value={KindFilter.Individual}>Individuals</option>}
	</select>
);

export const ReasonerSelect = ({
	value,
	onChange,
	reasoners,
}: {
	value: ReasonerBackend;
	onChange: (value: ReasonerBackend) => void;
	reasoners: ReasonersResponse | null;
}) => {
	const hermit = reasoners?.backends.hermit;
	return (
		<select
			aria-label="Reasoner"
			value={value}
			onChange={(e) => onChange(e.target.value as ReasonerBackend)}
			className={selectClass}
		>
			<option value={ReasonerBackend.Auto}>Auto</option>
			<option value={ReasonerBackend.OwlRl}>OWL RL (pure Python)</option>
			<option value={ReasonerBackend.Hermit} disabled={hermit != null && !hermit.available}>
				HermiT (OWL DL){hermit != null && !hermit.available ? ' — needs Java' : ''}
			</option>
		</select>
	);
};

/** Code with a copy button, and optionally a button that applies it. */
export const CodeBlock = ({
	code,
	label,
	onApply,
	applyLabel = 'Add to ontology',
	applying = false,
}: {
	code: string;
	label: string;
	onApply?: () => void;
	applyLabel?: string;
	applying?: boolean;
}) => (
	<div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
		<div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-800/60">
			<span className="text-[11px] font-medium tracking-wide text-secondary uppercase dark:text-slate-400">
				{label}
			</span>
			<div className="flex items-center gap-1">
				<CopyButton text={code} />
				{onApply && (
					<Button
						size={Size.SMALL}
						theme={ButtonTheme.Soft}
						onClick={onApply}
						loading={applying}
					>
						{applyLabel}
					</Button>
				)}
			</div>
		</div>
		<pre className="max-h-80 overflow-auto bg-white p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-body dark:bg-slate-900 dark:text-slate-300">
			{code}
		</pre>
	</div>
);

const termText = (term: SparqlTerm | null): string => {
	if (term == null) return '';
	if (term.type === 'iri') return term.name ?? term.value;
	return term.value;
};

/** SELECT rows as a table, ASK as yes/no, CONSTRUCT as triples. */
export const SparqlResultView = ({
	result,
	onOpen,
}: {
	result: SparqlResult;
	onOpen?: (iri: string) => void;
}) => {
	const [showAll, setShowAll] = useState(false);
	if (result.type === 'ask') {
		return (
			<p className="text-sm font-medium text-heading dark:text-slate-100">
				{result.boolean ? 'Yes' : 'No'}
			</p>
		);
	}
	const header = result.type === 'select' ? result.variables : ['subject', 'predicate', 'object'];
	const rows: (SparqlTerm | null)[][] =
		result.type === 'select'
			? result.rows.map((row) => result.variables.map((v) => row[v] ?? null))
			: result.triples;
	if (rows.length === 0) {
		return <p className="text-sm text-secondary dark:text-slate-400">No rows.</p>;
	}
	const shown = showAll ? rows : rows.slice(0, 50);
	return (
		<div className="flex flex-col gap-2">
			<div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
				<table className="w-full text-left text-xs">
					<thead className="bg-slate-50 text-secondary dark:bg-slate-800/60 dark:text-slate-400">
						<tr>
							{header.map((h) => (
								<th key={h} className="px-3 py-2 font-medium">
									{h}
								</th>
							))}
						</tr>
					</thead>
					<tbody className="divide-y divide-slate-100 dark:divide-slate-800">
						{shown.map((row, i) => (
							<tr key={i}>
								{row.map((term, j) => (
									<td
										key={j}
										className="px-3 py-1.5 align-top text-body dark:text-slate-300"
									>
										{term?.type === 'iri' && onOpen ? (
											<button
												type="button"
												title={term.value}
												onClick={() => onOpen(term.value)}
												className="cursor-pointer text-left text-brand-strong hover:underline dark:text-brand-light"
											>
												{termText(term)}
											</button>
										) : (
											<span title={term?.value}>{termText(term)}</span>
										)}
									</td>
								))}
							</tr>
						))}
					</tbody>
				</table>
			</div>
			<div className="flex items-center gap-3 text-xs text-secondary dark:text-slate-400">
				<span>
					{rows.length} {rows.length === 1 ? 'row' : 'rows'}
					{result.truncated ? ' (truncated by the server)' : ''}
				</span>
				{rows.length > 50 && (
					<Button
						size={Size.SMALL}
						theme={ButtonTheme.Minimal}
						onClick={() => setShowAll(!showAll)}
					>
						{showAll ? 'Show fewer' : 'Show all'}
					</Button>
				)}
			</div>
		</div>
	);
};

/** Save text as a file in the browser. */
export const downloadText = (text: string, filename: string, type = 'text/plain') => {
	const url = URL.createObjectURL(new Blob([text], { type }));
	const link = document.createElement('a');
	link.href = url;
	link.download = filename;
	link.click();
	URL.revokeObjectURL(url);
};

/** A row of chips for element references, or a dash when there are none. */
export const RefList = ({
	values,
	onOpen,
	empty = '—',
}: {
	values: OntoRef[];
	onOpen?: (iri: string) => void;
	empty?: string;
}) =>
	values.length === 0 ? (
		<span className="text-xs text-secondary dark:text-slate-500">{empty}</span>
	) : (
		<div className="flex flex-wrap gap-1.5">
			{values.map((v) => (
				<RefChip key={v.iri} value={v} onOpen={onOpen} />
			))}
		</div>
	);

/** A label over a big number, for result summaries. */
export const StatTile = ({
	label,
	value,
	tone = 'neutral',
}: {
	label: string;
	value: ReactNode;
	tone?: 'neutral' | 'good' | 'bad';
}) => {
	const toneClass =
		tone === 'good'
			? 'text-emerald-700 dark:text-emerald-300'
			: tone === 'bad'
				? 'text-red-700 dark:text-red-300'
				: 'text-heading dark:text-slate-100';
	return (
		<div className="rounded-xl border border-slate-200 px-3 py-2.5 dark:border-slate-800">
			<div className="text-[11px] font-medium text-secondary dark:text-slate-400">
				{label}
			</div>
			<div className={`mt-0.5 text-lg font-semibold tabular-nums ${toneClass}`}>{value}</div>
		</div>
	);
};

/** A labelled switch. */
export const ToggleField = ({
	label,
	checked,
	onChange,
	disabled = false,
}: {
	label: string;
	checked: boolean;
	onChange: (value: boolean) => void;
	disabled?: boolean;
}) => (
	<span className="inline-flex items-center gap-2 text-xs text-body dark:text-slate-300">
		<Toggle checked={checked} onChange={onChange} disabled={disabled} aria-label={label} />
		{label}
	</span>
);

/** Horizontal tabs; the active one is underlined. */
export const TabBar = <T extends string>({
	tabs,
	active,
	onChange,
}: {
	tabs: { id: T; label: string }[];
	active: T;
	onChange: (id: T) => void;
}) => (
	<nav
		role="tablist"
		aria-label="Ontology tools"
		className="flex gap-1 overflow-x-auto border-b border-slate-200 px-6 dark:border-slate-800"
	>
		{tabs.map((tab) => {
			const selected = tab.id === active;
			return (
				<button
					key={tab.id}
					type="button"
					role="tab"
					aria-selected={selected}
					onClick={() => onChange(tab.id)}
					className={`-mb-px cursor-pointer border-b-2 px-3 py-2.5 text-sm whitespace-nowrap transition-colors ${
						selected
							? 'border-brand font-medium text-heading dark:text-slate-100'
							: 'border-transparent text-secondary hover:text-body dark:text-slate-400 dark:hover:text-slate-200'
					}`}
				>
					{tab.label}
				</button>
			);
		})}
	</nav>
);

/**
 * Pick one element by typing part of its name. Matches come from the
 * elements route, so this scales to ontologies of any size.
 */
export const ElementPicker = ({
	ontologyId,
	filter,
	value,
	onChange,
	placeholder = 'Type to find an element',
}: {
	ontologyId: string;
	filter: KindFilter;
	value: OntoRef | null;
	onChange: (value: OntoRef | null) => void;
	placeholder?: string;
}) => {
	const [text, setText] = useState('');
	const [open, setOpen] = useState(false);
	const { data, isFetching } = useQuery({
		...ontologyQueries.elements(ontologyId, filter, text.trim()),
		enabled: open && text.trim().length > 0,
	});
	if (value) {
		return (
			<div className="flex items-center gap-2">
				<RefChip value={value} />
				<Button
					size={Size.SMALL}
					theme={ButtonTheme.Minimal}
					onClick={() => onChange(null)}
				>
					Change
				</Button>
			</div>
		);
	}
	const matches = (data?.elements ?? []).slice(0, 8);
	return (
		<div className="relative">
			<input
				className={inputClass}
				value={text}
				placeholder={placeholder}
				onChange={(e) => {
					setText(e.target.value);
					setOpen(true);
				}}
				onFocus={() => setOpen(true)}
				onBlur={() => setTimeout(() => setOpen(false), 150)}
				aria-label={placeholder}
			/>
			{open && text.trim() && (
				<ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
					{matches.length === 0 ? (
						<li className="px-3 py-2 text-xs text-secondary dark:text-slate-400">
							{isFetching ? 'Searching…' : 'No matching elements.'}
						</li>
					) : (
						matches.map((m) => (
							<li key={m.iri}>
								<button
									type="button"
									onMouseDown={(e) => e.preventDefault()}
									onClick={() => {
										onChange({ iri: m.iri, name: m.name });
										setText('');
										setOpen(false);
									}}
									className="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-sm text-body hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
								>
									<KindBadge kind={m.kind} />
									<span className="truncate">{m.name}</span>
								</button>
							</li>
						))
					)}
				</ul>
			)}
		</div>
	);
};

/** A collapsible block, closed by default. */
export const Disclosure = ({ summary, children }: { summary: ReactNode; children: ReactNode }) => (
	<details className="group rounded-lg border border-slate-200 dark:border-slate-700">
		<summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-secondary select-none group-open:border-b group-open:border-slate-200 hover:text-body dark:text-slate-400 dark:group-open:border-slate-700 dark:hover:text-slate-200">
			<span className="mr-1 inline-block transition-transform group-open:rotate-90">›</span>
			{summary}
		</summary>
		<div className="p-3">{children}</div>
	</details>
);
