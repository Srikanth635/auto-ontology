// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useCallback, useEffect, useState } from 'react';
import { modelSettingsApi } from '@/api/modelSettings';
import { Button } from '@/common/Button';
import { SkeletonCard } from '@/common/Skeleton';
import { Toast } from '@/common/Toast';
import { ButtonTheme, Size } from '@/enums/button';
import { ToastVariant } from '@/enums/toast';
import type {
	ModelRoleId,
	ModelSettingSaveResult,
	ModelSettingsPayload,
	ReembedStatus,
} from '@/types/modelSettings';
import { ModelRoleCard } from './ModelRoleCard';

const ROLE_ORDER: ModelRoleId[] = ['chat', 'fast_chat', 'embedding', 'rerank'];
const POLL_MS = 5000;

const formatTime = (iso: string | null): string => (iso ? new Date(iso).toLocaleString() : '');

export default function ModelSettingsPage() {
	const [payload, setPayload] = useState<ModelSettingsPayload | null>(null);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [reembed, setReembed] = useState<ReembedStatus | null>(null);
	const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);
	// Bumped on every save so each card re-mounts from what was stored.
	const [revision, setRevision] = useState(0);

	const apply = useCallback((res: Awaited<ReturnType<typeof modelSettingsApi.getAll>>) => {
		if (res.error) {
			setLoadError(res.message ?? 'Could not load model settings.');
			return;
		}
		setPayload(res);
		setReembed(res.reembed);
		setLoadError(null);
	}, []);

	const load = useCallback(async () => apply(await modelSettingsApi.getAll()), [apply]);

	useEffect(() => {
		let cancelled = false;
		modelSettingsApi.getAll().then((res) => {
			if (!cancelled) apply(res);
		});
		return () => {
			cancelled = true;
		};
	}, [apply]);

	// Poll only while a re-embed is running, and stop when it finishes.
	useEffect(() => {
		if (!reembed?.running) return;
		const timer = window.setInterval(async () => {
			const res = await modelSettingsApi.reembedStatus();
			if (!res.error) setReembed(res);
		}, POLL_MS);
		return () => window.clearInterval(timer);
	}, [reembed?.running]);

	const handleSaved = async (result: ModelSettingSaveResult) => {
		setToast({
			ok: true,
			message: result.reembed_triggered
				? 'Saved. Re-embedding all data with the new model in the background.'
				: 'Saved. The new model is used from the next request.',
		});
		await load();
		setRevision((current) => current + 1);
		if (result.reembed_triggered) {
			setReembed((current) => ({
				running: true,
				last_started_at: new Date().toISOString(),
				last_finished_at: current?.last_finished_at ?? null,
				last_error: null,
			}));
		}
	};

	const startReembed = async () => {
		const res = await modelSettingsApi.reembed();
		if (res.error) {
			setToast({ ok: false, message: res.message ?? 'Could not start re-embedding.' });
			return;
		}
		setReembed((current) => ({
			running: true,
			last_started_at: new Date().toISOString(),
			last_finished_at: current?.last_finished_at ?? null,
			last_error: null,
		}));
	};

	return (
		<main className="min-h-0 min-w-0 flex-1 overflow-y-auto bg-canvas px-7 py-6 sm:px-10 sm:py-7">
			<div className="w-full max-w-4xl space-y-5">
				<div>
					<h1 className="text-base font-semibold text-heading dark:text-slate-100">
						Models
					</h1>
					<p className="mt-1 text-xs text-secondary dark:text-slate-400">
						Choose the provider and model for each job. OpenAI, Anthropic and any
						OpenAI-compatible server (Ollama, vLLM, LM Studio, OpenRouter) are
						supported. Changes apply from the next request — no restart needed.
					</p>
				</div>

				{reembed ? (
					<div className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs shadow-sm dark:border-slate-700/80 dark:bg-slate-900/60">
						<div className="min-w-0 text-body dark:text-slate-300">
							{reembed.running ? (
								<span className="inline-flex items-center gap-2">
									<span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
									Re-embedding all data with the current embedding model…
								</span>
							) : reembed.last_error ? (
								<span className="text-red-600 dark:text-red-300">
									The last re-embed failed: {reembed.last_error}
								</span>
							) : reembed.last_finished_at ? (
								<span>
									Vectors last rebuilt {formatTime(reembed.last_finished_at)}.
								</span>
							) : (
								<span>Vectors are built with the current embedding model.</span>
							)}
						</div>
						<Button
							theme={ButtonTheme.Outline}
							size={Size.SMALL}
							type="button"
							disabled={reembed.running}
							onClick={() => void startReembed()}
						>
							Re-embed now
						</Button>
					</div>
				) : null}

				{loadError ? (
					<p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">
						{loadError}
					</p>
				) : null}

				{payload == null && !loadError ? (
					<div className="space-y-4" role="status" aria-label="Loading model settings">
						{ROLE_ORDER.map((role) => (
							<SkeletonCard key={role} className="h-48" />
						))}
					</div>
				) : null}

				{payload
					? ROLE_ORDER.map((role) => {
							const setting = payload.data.find((item) => item.role === role);
							const roleInfo = payload.roles[role];
							if (!setting || !roleInfo) return null;
							return (
								<ModelRoleCard
									key={`${role}:${revision}`}
									setting={setting}
									roleInfo={roleInfo}
									providers={payload.providers}
									onSaved={(result) => void handleSaved(result)}
									onError={(message) => setToast({ ok: false, message })}
								/>
							);
						})
					: null}
			</div>

			<Toast
				open={toast !== null}
				message={toast?.message ?? ''}
				variant={toast?.ok ? ToastVariant.Success : ToastVariant.Error}
				onClose={() => setToast(null)}
			/>
		</main>
	);
}
