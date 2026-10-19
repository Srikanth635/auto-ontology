// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useRef, useState, type DragEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { neemFilesApi } from '@/api/neemFiles';
import { Button } from '@/common/Button';
import { Icon, IconName } from '@/common/icons';
import { ConfirmModal } from '@/common/modal';
import { ProgressBar } from '@/common/ProgressBar';
import { Spinner } from '@/common/Spinner';
import { ButtonTheme, Size } from '@/enums/button';
import { NeemFileState } from '@/enums/neemFiles';
import { ProgressBarKind } from '@/enums/progressBar';
import type { NeemFile, NeemFolder } from '@/types/neemFiles';

const ACCEPTED_SUFFIXES = ['.sqlite', '.sqlite3', '.db', '.sql'];
const NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._ -]{0,199}$/;

// Fast while something is moving, slow otherwise: the slow poll is what
// notices a file copied into the folder by hand.
const BUSY_POLL_MS = 2000;
const IDLE_POLL_MS = 10000;

type Upload = { name: string; progress: number; error?: string };

const NEEM_FILES_QUERY_KEY = ['neem-files'];

const isBusy = (folder: NeemFolder | undefined): boolean =>
	folder?.catalog === 'ingesting' ||
	(folder?.files ?? []).some(
		(f) => f.state === NeemFileState.Waiting || f.state === NeemFileState.Loading,
	);

const formatBytes = (bytes: number): string => {
	if (bytes < 1024) return `${bytes} B`;
	const units = ['KB', 'MB', 'GB'];
	let value = bytes / 1024;
	let unit = 0;
	while (value >= 1024 && unit < units.length - 1) {
		value /= 1024;
		unit += 1;
	}
	return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
};

const rejectionReason = (file: File, maxBytes: number): string | null => {
	const lower = file.name.toLowerCase();
	if (!ACCEPTED_SUFFIXES.some((suffix) => lower.endsWith(suffix))) {
		return 'Only .sqlite, .sqlite3, .db and .sql files are accepted.';
	}
	if (!NAME_PATTERN.test(file.name)) {
		return 'Rename the file to letters, digits, spaces, ".", "-" and "_" only.';
	}
	if (file.size > maxBytes) return `Larger than the ${formatBytes(maxBytes)} limit.`;
	return null;
};

const STATE_LABEL: Record<NeemFileState, string> = {
	[NeemFileState.Waiting]: 'Waiting',
	[NeemFileState.Loading]: 'Merging',
	[NeemFileState.Loaded]: 'Merged',
	[NeemFileState.Failed]: 'Failed',
	[NeemFileState.Unknown]: 'Unknown',
};

const StateBadge = ({ file }: { file: NeemFile }) => {
	const busy = file.state === NeemFileState.Waiting || file.state === NeemFileState.Loading;
	const tone =
		file.state === NeemFileState.Loaded
			? 'bg-brand/10 text-brand-strong dark:text-brand-light'
			: file.state === NeemFileState.Failed
				? 'bg-red-500/10 text-red-700 dark:text-red-400'
				: 'bg-slate-100 text-body dark:bg-slate-800 dark:text-slate-300';
	return (
		<span
			className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}
		>
			{busy && <Spinner className="h-3 w-3" />}
			{file.state === NeemFileState.Loaded && (
				<Icon name={IconName.Check} className="h-3 w-3" />
			)}
			{STATE_LABEL[file.state] ?? file.state}
		</span>
	);
};

export const NeemFilesView = () => {
	const [uploads, setUploads] = useState<Upload[]>([]);
	const [isDragOver, setIsDragOver] = useState(false);
	const [deleting, setDeleting] = useState<string | null>(null);
	const [deleteError, setDeleteError] = useState<string | null>(null);
	const [confirming, setConfirming] = useState(false);
	const inputRef = useRef<HTMLInputElement>(null);
	const uploading = uploads.some((u) => u.error == null);

	const {
		data: folder = null,
		error: loadError,
		refetch,
	} = useQuery({
		queryKey: NEEM_FILES_QUERY_KEY,
		queryFn: async (): Promise<NeemFolder> => {
			const res = await neemFilesApi.list();
			if (res.error) throw new Error(res.message ?? 'Could not read the NEEM folder.');
			return res;
		},
		refetchInterval: (query) =>
			uploading || isBusy(query.state.data) ? BUSY_POLL_MS : IDLE_POLL_MS,
	});
	const refresh = () => void refetch();

	const uploadAll = async (picked: File[]) => {
		if (!folder) return;
		const maxBytes = folder.max_upload_bytes;
		setUploads((current) => [
			...current.filter((u) => !picked.some((f) => f.name === u.name)),
			...picked.map((f) => ({
				name: f.name,
				progress: 0,
				error: rejectionReason(f, maxBytes) ?? undefined,
			})),
		]);
		// One at a time: each is written to the folder in full before the
		// next starts, so the watcher sees them complete in order.
		for (const file of picked) {
			if (rejectionReason(file, maxBytes) != null) continue;
			const res = await neemFilesApi.upload(file, (progress) =>
				setUploads((current) =>
					current.map((u) => (u.name === file.name ? { ...u, progress } : u)),
				),
			);
			setUploads((current) =>
				res.error
					? current.map((u) =>
							u.name === file.name
								? { ...u, error: res.message ?? 'Upload failed.' }
								: u,
						)
					: current.filter((u) => u.name !== file.name),
			);
			refresh();
		}
	};

	const onDrop = (event: DragEvent<HTMLDivElement>) => {
		event.preventDefault();
		setIsDragOver(false);
		void uploadAll(Array.from(event.dataTransfer.files ?? []));
	};

	const confirmDelete = async () => {
		if (deleting == null) return;
		setConfirming(true);
		const res = await neemFilesApi.remove(deleting);
		setConfirming(false);
		if (res.error) {
			setDeleteError(res.message ?? 'Could not delete the file.');
			return;
		}
		setDeleting(null);
		setDeleteError(null);
		refresh();
	};

	if (loadError != null && folder == null) {
		return (
			<div className="mx-auto max-w-2xl p-6">
				<p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
					{loadError.message}
				</p>
			</div>
		);
	}

	if (folder && !folder.enabled) {
		return (
			<div className="mx-auto max-w-2xl p-6">
				<h1 className="mb-1 text-lg font-semibold text-heading dark:text-slate-100">
					NEEM Files
				</h1>
				<p className="text-sm text-body dark:text-slate-300">
					No NEEM folder is configured. Set <code>NEEM_DATA_DIR</code> for the API server
					and the ingestion service (Docker Compose sets it to <code>/data</code>).
				</p>
			</div>
		);
	}

	const files = folder?.files ?? [];

	return (
		<div className="h-full overflow-auto p-6">
			<div className="mx-auto max-w-2xl">
				<h1 className="mb-1 text-lg font-semibold text-heading dark:text-slate-100">
					NEEM Files
				</h1>
				<p className="mb-4 text-xs text-secondary">
					Every NEEM here is merged into one database,{' '}
					<strong className="text-body dark:text-slate-300">
						{folder?.database ?? 'neem'}
					</strong>
					, which is re-read into the catalog after each change. Files copied straight
					into the repo&apos;s <code>data/</code> folder are picked up the same way. Each
					row records the NEEM it came from in <code>neem_source_id</code>.
				</p>

				<div
					role="button"
					tabIndex={0}
					aria-label="Upload NEEM files"
					onClick={() => inputRef.current?.click()}
					onKeyDown={(event) => {
						if (event.key !== 'Enter' && event.key !== ' ') return;
						event.preventDefault();
						inputRef.current?.click();
					}}
					onDragOver={(event) => {
						event.preventDefault();
						setIsDragOver(true);
					}}
					onDragLeave={(event) => {
						event.preventDefault();
						setIsDragOver(false);
					}}
					onDrop={onDrop}
					className={`mb-5 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-10 text-center transition-colors focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:outline-none ${
						isDragOver
							? 'border-brand bg-brand/5'
							: 'border-slate-300 hover:border-slate-400 dark:border-slate-600 dark:hover:border-slate-500'
					}`}
				>
					<Icon
						name={IconName.Upload}
						className="h-6 w-6 text-secondary dark:text-slate-500"
					/>
					<p className="text-sm text-body dark:text-slate-300">
						<span className="font-medium text-brand-strong dark:text-brand-light">
							Drop NEEM files here
						</span>{' '}
						or click to choose
					</p>
					<p className="text-xs text-secondary">
						SQLite databases (.sqlite, .sqlite3, .db) or SQLite .sql dumps
						{folder ? `, up to ${formatBytes(folder.max_upload_bytes)} each` : ''}
					</p>
					<input
						ref={inputRef}
						type="file"
						multiple
						accept={ACCEPTED_SUFFIXES.join(',')}
						className="hidden"
						onChange={(event) => {
							void uploadAll(Array.from(event.target.files ?? []));
							event.target.value = '';
						}}
					/>
				</div>

				{uploads.length > 0 && (
					<ul className="mb-5 flex flex-col gap-2" aria-label="Uploads">
						{uploads.map((upload) => (
							<li
								key={upload.name}
								className="rounded-lg border border-slate-200 px-4 py-3 dark:border-slate-700"
							>
								{upload.error ? (
									<div className="flex items-start justify-between gap-3">
										<div className="min-w-0">
											<p className="truncate text-sm font-medium text-heading dark:text-slate-100">
												{upload.name}
											</p>
											<p className="text-xs text-red-700 dark:text-red-400">
												{upload.error}
											</p>
										</div>
										<Button
											theme={ButtonTheme.IconNeutral}
											size={Size.SMALL}
											iconOnly
											aria-label={`Dismiss ${upload.name}`}
											onClick={() =>
												setUploads((current) =>
													current.filter((u) => u.name !== upload.name),
												)
											}
										>
											<Icon name={IconName.Close} className="h-3.5 w-3.5" />
										</Button>
									</div>
								) : (
									<ProgressBar
										aria-label={`Uploading ${upload.name}`}
										label={`Uploading ${upload.name}`}
										value={Math.round(upload.progress * 100)}
										showValue
									/>
								)}
							</li>
						))}
					</ul>
				)}

				{folder?.catalog === 'ingesting' && (
					<div className="mb-3 flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-3 text-sm text-body dark:border-slate-700 dark:text-slate-300">
						<Spinner className="h-4 w-4 text-brand" />
						Updating the catalog for {folder.database}…
					</div>
				)}

				{folder == null ? (
					<div className="flex justify-center py-8">
						<ProgressBar kind={ProgressBarKind.Indeterminate} aria-label="Loading" />
					</div>
				) : files.length === 0 ? (
					<p className="py-6 text-center text-sm text-secondary">No NEEM files yet.</p>
				) : (
					<ul
						className="divide-y divide-slate-200 rounded-lg border border-slate-200 dark:divide-slate-700 dark:border-slate-700"
						aria-label="NEEM files"
					>
						{files.map((file) => (
							<li
								key={file.name}
								className="flex items-start justify-between gap-3 px-4 py-3"
							>
								<div className="min-w-0 flex-1">
									<div className="flex items-center gap-2">
										<span className="truncate text-sm font-medium text-heading dark:text-slate-100">
											{file.name}
										</span>
										<StateBadge file={file} />
									</div>
									<p className="text-xs text-secondary">
										{formatBytes(file.size)}
										{file.rows != null &&
											` · ${file.rows.toLocaleString()} rows`}
									</p>
									{file.error && (
										<p className="mt-1 text-xs break-words text-red-700 dark:text-red-400">
											{file.error}
										</p>
									)}
								</div>
								<Button
									theme={ButtonTheme.IconDanger}
									size={Size.SMALL}
									iconOnly
									aria-label={`Delete ${file.name}`}
									onClick={() => setDeleting(file.name)}
								>
									<Icon name={IconName.Trash} className="h-3.5 w-3.5" />
								</Button>
							</li>
						))}
					</ul>
				)}
			</div>

			<ConfirmModal
				open={deleting != null}
				title="Delete NEEM File"
				message={
					<>
						Delete <strong>{deleting}</strong> from the folder? Its rows are removed
						from {folder?.database ?? 'the merged database'} as well.
					</>
				}
				confirming={confirming}
				error={deleteError}
				onConfirm={confirmDelete}
				onCancel={() => {
					setDeleting(null);
					setDeleteError(null);
				}}
			/>
		</div>
	);
};
