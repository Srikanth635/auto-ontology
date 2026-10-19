// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useCallback, useRef, useState, type DragEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { dataFilesApi } from '@/api/dataFiles';
import { ConfirmModal } from '@/common/modal';
import { Icon, IconName } from '@/common/icons';
import { Spinner } from '@/common/Spinner';
import { dataFileQueries } from '@/lib/queries/dataFiles';
import type { DataFile, DataFileStatus } from '@/types/dataFile';

/** What the folder takes; the server checks the contents as well. */
const ACCEPT = '.sqlite,.sqlite3,.db,.duckdb,.sql';

type Upload = { id: number; name: string; progress: number; error: string | null };

const STATUS_LABEL: Record<DataFileStatus, string> = {
	pending: 'Waiting',
	converting: 'Converting',
	ingesting: 'Reading',
	ready: 'Ready',
	missing: 'File missing',
	failed: 'Failed',
};

const STATUS_STYLE: Record<DataFileStatus, string> = {
	pending: 'bg-slate-100 text-secondary dark:bg-slate-800 dark:text-slate-400',
	converting: 'bg-brand/10 text-brand-strong dark:text-brand-light',
	ingesting: 'bg-brand/10 text-brand-strong dark:text-brand-light',
	ready: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400',
	missing: 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400',
	failed: 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400',
};

const isInProgress = (status: DataFileStatus) =>
	status === 'pending' || status === 'converting' || status === 'ingesting';

const formatSize = (bytes: number | null): string => {
	if (bytes == null) return '';
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
	if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
};

let nextUploadId = 0;

const StatusBadge = ({ file }: { file: DataFile }) => (
	<span
		className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[file.status]}`}
	>
		{isInProgress(file.status) && file.status !== 'pending' ? (
			<Spinner className="h-3 w-3" />
		) : null}
		{STATUS_LABEL[file.status]}
	</span>
);

/**
 * Where database files are added: drop them on the page, or put them in the
 * data folder. Either way they end up in the same place, and the ingestion
 * service takes it from there, so this only stores files and shows how far each
 * one has got.
 */
export const DataFilesPanel = () => {
	const queryClient = useQueryClient();
	const inputRef = useRef<HTMLInputElement>(null);
	const { data: files = [], error: loadError } = useQuery(dataFileQueries.list());

	const [dragging, setDragging] = useState(false);
	const [uploads, setUploads] = useState<Upload[]>([]);
	const [removing, setRemoving] = useState<string | null>(null);
	const [removeBusy, setRemoveBusy] = useState(false);
	const [removeError, setRemoveError] = useState<string | null>(null);

	const refreshList = useCallback(
		() => queryClient.invalidateQueries({ queryKey: dataFileQueries.list().queryKey }),
		[queryClient],
	);

	const patchUpload = (id: number, patch: Partial<Upload>) =>
		setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, ...patch } : u)));

	const uploadAll = async (picked: File[]) => {
		const queued = picked.map((file) => ({
			file,
			upload: { id: nextUploadId++, name: file.name, progress: 0, error: null } as Upload,
		}));
		setUploads((prev) => [...prev, ...queued.map((q) => q.upload)]);

		// One at a time: a large database already fills the connection, and
		// the folder watcher then sees each file settle in turn.
		for (const { file, upload } of queued) {
			const res = await dataFilesApi.upload(file, (fraction) =>
				patchUpload(upload.id, { progress: fraction }),
			);
			if (res.error) {
				patchUpload(upload.id, { error: res.message ?? 'Upload failed.' });
				continue;
			}
			setUploads((prev) => prev.filter((u) => u.id !== upload.id));
			await refreshList();
		}
	};

	const onDrop = (event: DragEvent<HTMLDivElement>) => {
		event.preventDefault();
		setDragging(false);
		const dropped = Array.from(event.dataTransfer.files);
		if (dropped.length > 0) void uploadAll(dropped);
	};

	const confirmRemove = async () => {
		if (removing == null) return;
		setRemoveBusy(true);
		setRemoveError(null);
		const res = await dataFilesApi.remove(removing);
		setRemoveBusy(false);
		if (res.error) {
			setRemoveError(res.message ?? 'Failed to remove the file.');
			return;
		}
		setRemoving(null);
		await refreshList();
	};

	return (
		<section className="flex w-full flex-col gap-4" aria-label="Data files">
			<div>
				<h2 className="text-base font-semibold text-heading dark:text-slate-100">
					Data files
				</h2>
				<p className="mt-1 text-sm text-secondary dark:text-slate-400">
					Each SQLite or DuckDB file becomes its own database and is read automatically.
					You can also copy files into the <code>data/</code> folder of the project, or a
					SQLite <code>.sql</code> dump, which is converted first.
				</p>
			</div>

			<div
				role="button"
				tabIndex={0}
				aria-label="Add database files"
				onClick={() => inputRef.current?.click()}
				onKeyDown={(event) => {
					if (event.key === 'Enter' || event.key === ' ') {
						event.preventDefault();
						inputRef.current?.click();
					}
				}}
				onDragOver={(event) => {
					event.preventDefault();
					setDragging(true);
				}}
				onDragLeave={() => setDragging(false)}
				onDrop={onDrop}
				className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-9 text-center transition-colors ${
					dragging
						? 'border-brand bg-brand/5'
						: 'border-slate-300 bg-white hover:border-brand/60 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:hover:bg-slate-900/60'
				}`}
			>
				<Icon name={IconName.Upload} className="h-6 w-6 text-brand" />
				<p className="text-sm font-medium text-heading dark:text-slate-100">
					Drop database files here, or click to choose
				</p>
				<p className="text-xs text-secondary dark:text-slate-500">
					.sqlite, .db, .duckdb or a SQLite .sql dump
				</p>
				<input
					ref={inputRef}
					type="file"
					multiple
					accept={ACCEPT}
					className="hidden"
					onChange={(event) => {
						const chosen = Array.from(event.target.files ?? []);
						event.target.value = '';
						if (chosen.length > 0) void uploadAll(chosen);
					}}
				/>
			</div>

			{uploads.length > 0 ? (
				<ul className="flex flex-col gap-2">
					{uploads.map((upload) => (
						<li
							key={upload.id}
							className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-950"
						>
							<span className="min-w-0 flex-1 truncate text-heading dark:text-slate-100">
								{upload.name}
							</span>
							{upload.error ? (
								<>
									<span className="text-xs text-red-600 dark:text-red-400">
										{upload.error}
									</span>
									<button
										type="button"
										aria-label={`Dismiss ${upload.name}`}
										onClick={() =>
											setUploads((prev) =>
												prev.filter((u) => u.id !== upload.id),
											)
										}
										className="text-secondary hover:text-heading dark:text-slate-400"
									>
										<Icon name={IconName.Close} className="h-4 w-4" />
									</button>
								</>
							) : (
								<span className="flex w-40 items-center gap-2">
									<span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
										<span
											className="block h-full rounded-full bg-brand transition-[width]"
											style={{
												width: `${Math.round(upload.progress * 100)}%`,
											}}
										/>
									</span>
									<span className="w-9 text-right text-xs text-secondary tabular-nums dark:text-slate-400">
										{Math.round(upload.progress * 100)}%
									</span>
								</span>
							)}
						</li>
					))}
				</ul>
			) : null}

			{loadError ? (
				<p className="text-sm text-red-600 dark:text-red-400">{loadError.message}</p>
			) : null}

			{files.length > 0 ? (
				<ul className="flex flex-col divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-950">
					{files.map((file) => (
						<li key={file.name} className="flex items-center gap-3 px-4 py-3 text-sm">
							<Icon
								name={IconName.Database}
								className="h-4 w-4 shrink-0 text-secondary dark:text-slate-400"
							/>
							<div className="min-w-0 flex-1">
								<p className="truncate font-medium text-heading dark:text-slate-100">
									{file.name}
								</p>
								{file.error ? (
									<p className="truncate text-xs text-red-600 dark:text-red-400">
										{file.error}
									</p>
								) : null}
							</div>
							<span className="hidden shrink-0 text-xs text-secondary tabular-nums sm:inline dark:text-slate-500">
								{formatSize(file.size_bytes)}
							</span>
							<StatusBadge file={file} />
							<button
								type="button"
								aria-label={`Remove ${file.name}`}
								onClick={() => {
									setRemoveError(null);
									setRemoving(file.name);
								}}
								className="shrink-0 rounded-md p-1 text-secondary transition-colors hover:bg-slate-100 hover:text-red-600 dark:text-slate-400 dark:hover:bg-slate-800"
							>
								<Icon name={IconName.Trash} className="h-4 w-4" />
							</button>
						</li>
					))}
				</ul>
			) : null}

			<ConfirmModal
				open={removing !== null}
				title="Remove Data File"
				message={
					removing ? (
						<>
							Remove <strong>{removing}</strong>? The file is deleted from the data
							folder, and the database read from it is removed with everything built
							on it, including its descriptions. This action cannot be undone.
						</>
					) : null
				}
				confirmLabel="Remove"
				onConfirm={confirmRemove}
				onCancel={() => {
					if (removeBusy) return;
					setRemoving(null);
					setRemoveError(null);
				}}
				confirming={removeBusy}
				error={removeError}
			/>
		</section>
	);
};
