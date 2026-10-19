// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { ontologiesApi } from '@/api/ontologies';
import { Button } from '@/common/Button';
import { EmptyState } from '@/common/EmptyState';
import { FileUpload } from '@/common/FileUpload';
import { Icon, IconName } from '@/common/icons';
import { SkeletonBlock } from '@/common/Skeleton';
import { Toast } from '@/common/Toast';
import { ButtonTheme, Size } from '@/enums/button';
import { EmptyStateVariant } from '@/enums/emptyState';
import { ExportFormat, OntologyTab } from '@/enums/ontologies';
import { ToastVariant } from '@/enums/toast';
import { ontologyKeys, ontologyQueries } from '@/lib/queries/ontologies';
import type { OntologySummary } from '@/types/ontologies';

import { AlignTab } from './AlignTab';
import { AskTab } from './AskTab';
import { ExploreTab } from './ExploreTab';
import { FindTab } from './FindTab';
import { GrowTab } from './GrowTab';
import type { Notify } from './hooks';
import { ReasonTab } from './ReasonTab';
import {
	ErrorNote,
	Field,
	InfoNote,
	Panel,
	TabBar,
	inputClass,
	reasonerName,
	selectClass,
} from './ui';
import { ValidateTab } from './ValidateTab';

const TABS: { id: OntologyTab; label: string }[] = [
	{ id: OntologyTab.Explore, label: 'Explore' },
	{ id: OntologyTab.Ask, label: 'Ask' },
	{ id: OntologyTab.Find, label: 'Find' },
	{ id: OntologyTab.Reason, label: 'Reason' },
	{ id: OntologyTab.Grow, label: 'Grow' },
	{ id: OntologyTab.Align, label: 'Align' },
	{ id: OntologyTab.Validate, label: 'Validate' },
];

const ACCEPT = '.ttl,.owl,.rdf,.xml,.nt,.n3,.jsonld,.json,.trig';

const isTab = (value: string | null): value is OntologyTab => TABS.some((t) => t.id === value);

const UploadPanel = ({
	onCreated,
	onCancel,
}: {
	onCreated: (summary: OntologySummary) => void;
	onCancel?: () => void;
}) => {
	const [file, setFile] = useState<File | null>(null);
	const [title, setTitle] = useState('');
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const submit = async () => {
		if (!file) return;
		setBusy(true);
		setError(null);
		const res = await ontologiesApi.create(await file.text(), file.name, title.trim());
		setBusy(false);
		if (res.error) {
			setError(res.message ?? 'The ontology could not be loaded.');
			return;
		}
		onCreated(res);
	};

	return (
		<Panel
			title="Load an ontology"
			description="OWL or RDF as Turtle, RDF/XML, N-Triples, N3 or JSON-LD. Every class, property and individual is indexed for search; large files take a little while."
		>
			<div className="flex flex-col gap-4">
				<FileUpload
					value={file}
					onChange={setFile}
					accept={ACCEPT}
					description="Turtle (.ttl), RDF/XML (.owl, .rdf), N-Triples, N3, JSON-LD"
					aria-label="Ontology file"
				/>
				<Field label="Title (optional)">
					<input
						className={inputClass}
						value={title}
						onChange={(e) => setTitle(e.target.value)}
						placeholder="Taken from the ontology if left empty"
					/>
				</Field>
				<ErrorNote message={error} />
				<div className="flex gap-2">
					<Button onClick={submit} loading={busy} disabled={!file}>
						Load and index
					</Button>
					{onCancel && (
						<Button theme={ButtonTheme.Minimal} onClick={onCancel} disabled={busy}>
							Cancel
						</Button>
					)}
				</div>
			</div>
		</Panel>
	);
};

const OntologyHeader = ({
	ontology,
	onDeleted,
	notify,
}: {
	ontology: OntologySummary;
	onDeleted: () => void;
	notify: Notify;
}) => {
	const queryClient = useQueryClient();
	const [format, setFormat] = useState(ExportFormat.Turtle);
	const [confirming, setConfirming] = useState(false);
	const [busy, setBusy] = useState<'delete' | 'reindex' | null>(null);
	const counts = ontology.counts;
	const index = ontology.index;
	const reasoning = ontology.reasoning;

	const reindex = async () => {
		setBusy('reindex');
		const res = await ontologiesApi.reindex(ontology.id);
		setBusy(null);
		if (res.error) notify(res.message ?? 'Reindexing failed.', false);
		else notify(`Reindexed: ${res.embedded} embedded, ${res.reused} reused.`, true);
		void queryClient.invalidateQueries({ queryKey: ontologyKeys.one(ontology.id) });
	};

	const remove = async () => {
		setBusy('delete');
		const res = await ontologiesApi.remove(ontology.id);
		setBusy(null);
		setConfirming(false);
		if (res.error) {
			notify(res.message ?? 'Delete failed.', false);
			return;
		}
		notify(`Deleted ${ontology.title}.`, true);
		onDeleted();
	};

	const facts = counts
		? [
				`${counts.class} classes`,
				`${counts.object_property + counts.datatype_property + counts.annotation_property} properties`,
				`${counts.individual} individuals`,
				`${counts.triples} triples`,
			]
		: [];

	return (
		<div className="flex flex-col gap-3 px-6 pt-5 pb-4">
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div className="min-w-0">
					<h2 className="truncate text-xl font-semibold tracking-tight text-heading dark:text-slate-100">
						{ontology.title}
					</h2>
					{ontology.ontology_iri && (
						<code className="text-xs text-secondary dark:text-slate-400">
							{ontology.ontology_iri}
						</code>
					)}
				</div>
				<div className="flex flex-wrap items-center gap-2">
					<select
						aria-label="Export format"
						value={format}
						onChange={(e) => setFormat(e.target.value as ExportFormat)}
						className={`${selectClass} h-9 py-0`}
					>
						<option value={ExportFormat.Turtle}>Turtle</option>
						<option value={ExportFormat.RdfXml}>RDF/XML</option>
						<option value={ExportFormat.NTriples}>N-Triples</option>
						<option value={ExportFormat.JsonLd}>JSON-LD</option>
					</select>
					<a
						href={ontologiesApi.exportUrl(ontology.id, format)}
						download
						className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-body transition-colors hover:border-brand hover:bg-brand/10 hover:text-brand-strong dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
					>
						<Icon name={IconName.Download} className="h-4 w-4" />
						Export
					</a>
					<Button
						theme={ButtonTheme.Secondary}
						onClick={reindex}
						loading={busy === 'reindex'}
					>
						Reindex
					</Button>
					{confirming ? (
						<>
							<Button
								theme={ButtonTheme.Danger}
								onClick={remove}
								loading={busy === 'delete'}
							>
								Delete for good
							</Button>
							<Button
								theme={ButtonTheme.Minimal}
								onClick={() => setConfirming(false)}
							>
								Keep
							</Button>
						</>
					) : (
						<Button
							theme={ButtonTheme.IconDanger}
							iconOnly
							aria-label="Delete ontology"
							onClick={() => setConfirming(true)}
						>
							<Icon name={IconName.Trash} className="h-4 w-4" />
						</Button>
					)}
				</div>
			</div>
			<div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-secondary dark:text-slate-400">
				{facts.map((f) => (
					<span key={f}>{f}</span>
				))}
				{index && (
					<span>
						{index.dense
							? `Search: meaning + keywords (${index.vector_store})`
							: 'Search: keywords only'}
					</span>
				)}
				{reasoning && (
					<span
						className={
							reasoning.consistent
								? 'text-emerald-700 dark:text-emerald-300'
								: 'text-red-700 dark:text-red-300'
						}
					>
						{reasonerName(reasoning.backend)}:{' '}
						{reasoning.consistent ? 'consistent' : 'inconsistent'}
						{reasoning.unsatisfiable
							? `, ${reasoning.unsatisfiable} unsatisfiable`
							: ''}
					</span>
				)}
			</div>
			{index?.warnings.map((w) => (
				<InfoNote key={w}>{w}</InfoNote>
			))}
		</div>
	);
};

export const OntologiesView = () => {
	const router = useRouter();
	const pathname = usePathname();
	const params = useSearchParams();
	const queryClient = useQueryClient();
	const [uploading, setUploading] = useState(false);
	const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

	const list = useQuery(ontologyQueries.list());
	const reasoners = useQuery(ontologyQueries.reasoners());
	const ontologies = list.data ?? [];

	const requested = params.get('o');
	const selectedId =
		requested && ontologies.some((o) => o.id === requested)
			? requested
			: (ontologies[0]?.id ?? null);
	const tabParam = params.get('tab');
	const tab = isTab(tabParam) ? tabParam : OntologyTab.Explore;
	const iri = params.get('iri');

	const summary = useQuery({
		...ontologyQueries.summary(selectedId ?? ''),
		enabled: selectedId != null,
	});

	const navigate = useCallback(
		(next: { o?: string | null; tab?: OntologyTab; iri?: string | null }) => {
			const search = new URLSearchParams(params.toString());
			const set = (key: string, value: string | null | undefined) => {
				if (value === undefined) return;
				if (value === null) search.delete(key);
				else search.set(key, value);
			};
			set('o', next.o);
			set('tab', next.tab);
			set('iri', next.iri);
			router.replace(`${pathname}?${search.toString()}`, { scroll: false });
		},
		[params, pathname, router],
	);

	const notify: Notify = useCallback((message, ok = true) => setToast({ message, ok }), []);
	// Successes clear themselves; errors stay until dismissed.
	useEffect(() => {
		if (!toast?.ok) return;
		const timer = setTimeout(() => setToast(null), 4000);
		return () => clearTimeout(timer);
	}, [toast]);
	const openElement = useCallback(
		(target: string) => navigate({ tab: OntologyTab.Explore, iri: target }),
		[navigate],
	);

	const onCreated = (created: OntologySummary) => {
		setUploading(false);
		void queryClient.invalidateQueries({ queryKey: [...ontologyKeys.all, 'list'] });
		navigate({ o: created.id, tab: OntologyTab.Explore, iri: null });
		notify(`Loaded ${created.title}.`, true);
	};

	// Opening an element or another tab starts at the top, wherever the last
	// view was scrolled to.
	const mainRef = useRef<HTMLElement>(null);
	useEffect(() => {
		mainRef.current?.scrollTo({ top: 0 });
	}, [selectedId, tab, iri]);

	const selected = summary.data ?? ontologies.find((o) => o.id === selectedId) ?? null;
	const showUpload = uploading || (list.isSuccess && ontologies.length === 0);

	return (
		<div className="flex h-full w-full flex-col bg-white dark:bg-slate-950">
			<header className="flex items-center justify-between gap-3 border-b border-slate-200 px-6 py-4 dark:border-slate-800">
				<div className="flex items-center gap-3">
					<Icon
						name={IconName.Ontology}
						className="h-5 w-5 text-body dark:text-slate-300"
					/>
					<h1 className="text-lg font-semibold tracking-tight text-heading dark:text-slate-100">
						Ontologies
					</h1>
				</div>
				<Button
					size={Size.REGULAR}
					iconPosition="left"
					onClick={() => setUploading(true)}
					disabled={showUpload}
				>
					<Icon name={IconName.Upload} className="h-4 w-4" />
					Load ontology
				</Button>
			</header>

			<div className="flex min-h-0 flex-1">
				{ontologies.length > 0 && (
					<aside className="hidden w-60 shrink-0 overflow-y-auto border-r border-slate-200 p-3 md:block dark:border-slate-800">
						<ul className="flex flex-col gap-1">
							{ontologies.map((o) => (
								<li key={o.id}>
									<button
										type="button"
										onClick={() => {
											setUploading(false);
											navigate({ o: o.id, iri: null });
										}}
										className={`flex w-full cursor-pointer flex-col rounded-lg px-3 py-2 text-left transition-colors ${
											o.id === selectedId && !showUpload
												? 'bg-brand/10 dark:bg-brand/20'
												: 'hover:bg-slate-50 dark:hover:bg-slate-800/60'
										}`}
									>
										<span className="truncate text-sm font-medium text-heading dark:text-slate-100">
											{o.title}
										</span>
										<span className="truncate text-[11px] text-secondary dark:text-slate-500">
											{o.counts
												? `${o.counts.class} classes · ${o.filename || o.id}`
												: o.filename || o.id}
										</span>
									</button>
								</li>
							))}
						</ul>
					</aside>
				)}

				<main ref={mainRef} className="flex min-w-0 flex-1 flex-col overflow-y-auto">
					{list.isPending ? (
						<div className="flex flex-col gap-3 p-6">
							<SkeletonBlock className="h-7 w-64" />
							<SkeletonBlock className="h-4 w-96" />
						</div>
					) : list.error ? (
						<div className="p-6">
							<ErrorNote message={list.error.message} />
						</div>
					) : showUpload ? (
						<div className="mx-auto flex w-full max-w-2xl flex-col gap-5 p-6">
							{ontologies.length === 0 && (
								<EmptyState
									variant={EmptyStateVariant.Borderless}
									icon={IconName.Ontology}
									title="Work with an ontology you already have"
									description="Load an OWL/RDF ontology to search it, ask questions in plain language, run a reasoner, grow it, align it with another and validate data against it."
								/>
							)}
							<UploadPanel
								onCreated={onCreated}
								onCancel={
									ontologies.length > 0 ? () => setUploading(false) : undefined
								}
							/>
						</div>
					) : selected ? (
						<>
							<OntologyHeader
								ontology={selected}
								notify={notify}
								onDeleted={() => {
									queryClient.removeQueries({
										queryKey: ontologyKeys.one(selected.id),
									});
									void queryClient.invalidateQueries({
										queryKey: [...ontologyKeys.all, 'list'],
									});
									navigate({ o: null, iri: null });
								}}
							/>
							<TabBar
								tabs={TABS}
								active={tab}
								onChange={(id) => navigate({ tab: id })}
							/>
							<div className="flex min-h-0 flex-1 flex-col">
								{tab === OntologyTab.Explore && (
									<ExploreTab
										ontologyId={selected.id}
										iri={iri}
										onOpen={openElement}
									/>
								)}
								{tab === OntologyTab.Ask && (
									<AskTab
										ontologyId={selected.id}
										reasoners={reasoners.data ?? null}
										onOpen={openElement}
									/>
								)}
								{tab === OntologyTab.Find && (
									<FindTab ontologyId={selected.id} onOpen={openElement} />
								)}
								{tab === OntologyTab.Reason && (
									<ReasonTab
										ontologyId={selected.id}
										reasoners={reasoners.data ?? null}
										onOpen={openElement}
										notify={notify}
									/>
								)}
								{tab === OntologyTab.Grow && (
									<GrowTab
										ontologyId={selected.id}
										onOpen={openElement}
										notify={notify}
									/>
								)}
								{tab === OntologyTab.Align && (
									<AlignTab
										ontology={selected}
										ontologies={ontologies}
										onOpen={openElement}
										notify={notify}
									/>
								)}
								{tab === OntologyTab.Validate && (
									<ValidateTab ontologyId={selected.id} onOpen={openElement} />
								)}
							</div>
						</>
					) : null}
				</main>
			</div>

			<Toast
				open={toast != null}
				message={toast?.message ?? ''}
				variant={toast?.ok ? ToastVariant.Success : ToastVariant.Error}
				onClose={() => setToast(null)}
			/>
		</div>
	);
};
