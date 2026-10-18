// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useId, useMemo, useState } from 'react';
import { modelSettingsApi } from '@/api/modelSettings';
import { Button } from '@/common/Button';
import { ButtonTheme, Size } from '@/enums/button';
import type {
	ModelProviderId,
	ModelProviderInfo,
	ModelRoleId,
	ModelRoleInfo,
	ModelSetting,
	ModelSettingInput,
	ModelSettingSaveResult,
	ModelTestResult,
} from '@/types/modelSettings';

const ROLE_DESCRIPTIONS: Record<ModelRoleId, string> = {
	chat: 'Answers questions, writes SQL and builds the semantic layer.',
	fast_chat:
		'A cheaper model for entity extraction, follow-up questions and charts. Uses the chat model unless set.',
	embedding: 'Turns catalog and glossary text into vectors for search.',
	rerank: 'Optional. Orders candidates when linking bridge tables.',
};

const BASE_URL_PLACEHOLDERS: Partial<Record<ModelProviderId, string>> = {
	openai_compatible: 'http://localhost:11434/v1',
	rerank_api: 'https://api.cohere.com/v2',
};

const PROVIDER_HINTS: Partial<Record<ModelProviderId, string>> = {
	openai_compatible: 'Ollama, vLLM, LM Studio, OpenRouter, Azure or any OpenAI-style server.',
	rerank_api: 'Any /rerank API in the Cohere style: Cohere, Jina, Voyage, vLLM, Infinity.',
	none: 'Bridge tables keep their first candidate instead of a reranked one.',
};

/** Pseudo-provider for fast chat: reuse the chat model instead of choosing one. */
const SAME_AS_CHAT = 'same_as_chat';

const inputClass =
	'h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-body outline-none transition-colors placeholder:text-secondary focus:border-brand focus:ring-2 focus:ring-brand/25 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:disabled:bg-slate-800/50';

const labelClass = 'text-xs font-medium text-body dark:text-slate-300';

type StatusPill = { text: string; tone: 'ok' | 'warn' | 'muted' };

const statusOf = (setting: ModelSetting): StatusPill => {
	// Fast chat with nothing of its own saved always follows chat, configured or not.
	if (setting.role === 'fast_chat' && (setting.source === 'chat' || setting.source === 'unset'))
		return { text: 'Using chat model', tone: 'muted' };
	if (setting.role === 'rerank' && setting.provider === 'none')
		return { text: 'Off', tone: 'muted' };
	if (!setting.configured) return { text: 'Not configured', tone: 'warn' };
	if (setting.source === 'environment') return { text: 'From environment', tone: 'ok' };
	return { text: 'Configured', tone: 'ok' };
};

const pillClass: Record<StatusPill['tone'], string> = {
	ok: 'bg-brand-soft text-brand-strong dark:bg-brand/15 dark:text-brand',
	warn: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300',
	muted: 'bg-slate-100 text-secondary dark:bg-slate-800 dark:text-slate-400',
};

export type ModelRoleCardProps = {
	setting: ModelSetting;
	roleInfo: ModelRoleInfo;
	providers: Record<ModelProviderId, ModelProviderInfo>;
	onSaved: (result: ModelSettingSaveResult) => void;
	onError: (message: string) => void;
};

export const ModelRoleCard = ({
	setting,
	roleInfo,
	providers,
	onSaved,
	onError,
}: ModelRoleCardProps) => {
	const formId = useId();
	const isFastChat = setting.role === 'fast_chat';
	const usingChat = isFastChat && (setting.source === 'chat' || setting.source === 'unset');

	const [provider, setProvider] = useState<ModelProviderId | typeof SAME_AS_CHAT>(
		isFastChat && usingChat ? SAME_AS_CHAT : setting.provider,
	);
	const [model, setModel] = useState(usingChat ? '' : setting.model);
	const [baseUrl, setBaseUrl] = useState(setting.base_url);
	const [apiKey, setApiKey] = useState('');
	const [dimensions, setDimensions] = useState(
		setting.dimensions == null ? '' : String(setting.dimensions),
	);
	const [models, setModels] = useState<string[]>([]);
	const [busy, setBusy] = useState<'save' | 'test' | 'list' | null>(null);
	const [test, setTest] = useState<ModelTestResult | null>(null);

	const status = statusOf(setting);
	const realProvider = provider === SAME_AS_CHAT ? null : provider;
	const providerInfo = realProvider ? providers[realProvider] : null;
	const keepsStoredKey = setting.has_api_key && realProvider === setting.provider && !usingChat;
	const needsBaseUrl = realProvider === 'openai_compatible' || realProvider === 'rerank_api';
	const off = realProvider === 'none';
	const canList =
		realProvider != null && realProvider !== 'none' && realProvider !== 'rerank_api';

	const dimensionsValue = dimensions.trim() === '' ? null : Number(dimensions);
	const dimensionsValid =
		dimensionsValue == null ||
		(Number.isInteger(dimensionsValue) && dimensionsValue >= 1 && dimensionsValue <= 2048);

	const input = useMemo((): ModelSettingInput | null => {
		if (realProvider == null) return null;
		return {
			provider: realProvider,
			model: off ? '' : model.trim(),
			base_url: off ? '' : baseUrl.trim(),
			dimensions: setting.role === 'embedding' ? dimensionsValue : null,
			// Blank keeps the stored key; the backend drops it on a provider change.
			...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
		};
	}, [realProvider, off, model, baseUrl, setting.role, dimensionsValue, apiKey]);

	const missing = (() => {
		if (input == null || off) return null;
		if (!input.model) return 'Choose a model.';
		if (needsBaseUrl && !input.base_url) return 'Enter a base URL.';
		if (providerInfo?.key_required && !input.api_key && !keepsStoredKey)
			return 'Enter an API key.';
		if (!dimensionsValid) return 'Dimensions must be a whole number from 1 to 2048.';
		return null;
	})();

	const choose = (next: ModelProviderId | typeof SAME_AS_CHAT) => {
		setProvider(next);
		setTest(null);
		setModels([]);
		if (next !== setting.provider) {
			setModel('');
			setBaseUrl('');
		} else {
			setModel(usingChat ? '' : setting.model);
			setBaseUrl(setting.base_url);
		}
	};

	const save = async () => {
		setBusy('save');
		setTest(null);
		const res =
			provider === SAME_AS_CHAT
				? await modelSettingsApi.reset(setting.role)
				: input
					? await modelSettingsApi.save(setting.role, input)
					: null;
		setBusy(null);
		if (res == null) return;
		if (res.error) {
			onError(res.message ?? 'Saving failed.');
			return;
		}
		setApiKey('');
		onSaved(res);
	};

	const runTest = async () => {
		if (input == null) return;
		setBusy('test');
		const res = await modelSettingsApi.test(setting.role, input);
		setBusy(null);
		setTest(res.error ? { ok: false, detail: res.message ?? 'The test failed.' } : res);
	};

	const loadModels = async () => {
		if (input == null) return;
		setBusy('list');
		const res = await modelSettingsApi.listModels(setting.role, { ...input, model: '' });
		setBusy(null);
		if (res.error) {
			onError(res.message ?? 'Could not load models.');
			return;
		}
		setModels(res.models);
		if (res.models.length === 0) onError('The provider listed no models.');
	};

	const providerOptions: Array<ModelProviderId | typeof SAME_AS_CHAT> = isFastChat
		? [SAME_AS_CHAT, ...roleInfo.providers]
		: roleInfo.providers;

	return (
		<section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700/80 dark:bg-slate-900/60">
			<header className="flex items-start justify-between gap-4">
				<div className="min-w-0">
					<h2 className="text-sm font-semibold text-heading dark:text-slate-100">
						{roleInfo.label}
					</h2>
					<p className="mt-1 text-xs text-secondary dark:text-slate-400">
						{ROLE_DESCRIPTIONS[setting.role]}
					</p>
				</div>
				<span
					className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium ${pillClass[status.tone]}`}
				>
					{status.text}
				</span>
			</header>

			<div
				className="mt-4 flex flex-wrap gap-1.5"
				role="radiogroup"
				aria-label={`${roleInfo.label} provider`}
			>
				{providerOptions.map((option) => {
					const selected = option === provider;
					const label =
						option === SAME_AS_CHAT ? 'Same as chat' : providers[option].label;
					return (
						<button
							key={option}
							type="button"
							role="radio"
							aria-checked={selected}
							onClick={() => choose(option)}
							className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
								selected
									? 'border-brand bg-brand-soft text-brand-strong dark:bg-brand/15 dark:text-brand'
									: 'border-slate-200 text-body hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
							}`}
						>
							{label}
						</button>
					);
				})}
			</div>

			{realProvider && PROVIDER_HINTS[realProvider] ? (
				<p className="mt-2 text-xs text-secondary dark:text-slate-400">
					{PROVIDER_HINTS[realProvider]}
				</p>
			) : null}

			{realProvider && !off ? (
				<form
					id={formId}
					className="mt-4 grid gap-4 sm:grid-cols-2"
					onSubmit={(event) => {
						event.preventDefault();
						if (!missing) void save();
					}}
				>
					<div className="flex flex-col gap-1.5 sm:col-span-2">
						<label htmlFor={`${formId}-model`} className={labelClass}>
							Model
						</label>
						<div className="flex gap-2">
							<input
								id={`${formId}-model`}
								list={`${formId}-models`}
								value={model}
								onChange={(event) => setModel(event.target.value)}
								placeholder={
									setting.role === 'embedding'
										? 'e.g. text-embedding-3-small'
										: 'Type a model id or load the list'
								}
								className={inputClass}
								autoComplete="off"
							/>
							<datalist id={`${formId}-models`}>
								{models.map((id) => (
									<option key={id} value={id} />
								))}
							</datalist>
							{canList ? (
								<Button
									theme={ButtonTheme.Outline}
									size={Size.REGULAR}
									type="button"
									disabled={busy !== null}
									onClick={() => void loadModels()}
								>
									{busy === 'list' ? 'Loading…' : 'Load models'}
								</Button>
							) : null}
						</div>
						{models.length > 0 ? (
							<p className="text-xs text-secondary dark:text-slate-400">
								{models.length} model{models.length === 1 ? '' : 's'} available —
								start typing to pick one.
							</p>
						) : null}
					</div>

					<div className="flex flex-col gap-1.5">
						<label htmlFor={`${formId}-key`} className={labelClass}>
							API key
							{providerInfo?.key_required ? '' : ' (optional)'}
						</label>
						<input
							id={`${formId}-key`}
							type="password"
							value={apiKey}
							onChange={(event) => setApiKey(event.target.value)}
							placeholder={
								keepsStoredKey ? 'Stored — leave blank to keep' : 'Paste a key'
							}
							className={inputClass}
							autoComplete="new-password"
						/>
						<p className="text-[11px] text-secondary dark:text-slate-500">
							Stored encrypted. Never shown again after saving.
						</p>
					</div>

					<div className="flex flex-col gap-1.5">
						<label htmlFor={`${formId}-url`} className={labelClass}>
							Base URL{needsBaseUrl ? '' : ' (optional)'}
						</label>
						<input
							id={`${formId}-url`}
							value={baseUrl}
							onChange={(event) => setBaseUrl(event.target.value)}
							placeholder={
								BASE_URL_PLACEHOLDERS[realProvider] ??
								providerInfo?.default_base_url ??
								''
							}
							className={inputClass}
							autoComplete="off"
						/>
					</div>

					{setting.role === 'embedding' ? (
						<div className="flex flex-col gap-1.5">
							<label htmlFor={`${formId}-dims`} className={labelClass}>
								Dimensions (optional)
							</label>
							<input
								id={`${formId}-dims`}
								type="number"
								inputMode="numeric"
								min={1}
								max={2048}
								value={dimensions}
								onChange={(event) => setDimensions(event.target.value)}
								placeholder="Model default"
								aria-invalid={!dimensionsValid}
								className={`${inputClass} aria-[invalid=true]:border-red-500`}
							/>
							<p className="text-[11px] text-secondary dark:text-slate-500">
								Up to 2048. Needed for models wider than that, such as
								text-embedding-3-large.
							</p>
						</div>
					) : null}
				</form>
			) : null}

			{setting.role === 'embedding' ? (
				<p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-200">
					Changing the embedding model re-embeds all catalog and glossary data in the
					background. Search quality is reduced until it finishes.
				</p>
			) : null}

			{test ? (
				<p
					role="status"
					className={`mt-4 rounded-lg px-3 py-2 text-xs ${
						test.ok
							? 'bg-brand-soft text-brand-strong dark:bg-brand/15 dark:text-brand'
							: 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300'
					}`}
				>
					{test.detail}
				</p>
			) : null}

			<footer className="mt-4 flex items-center justify-end gap-2">
				{missing && provider !== SAME_AS_CHAT ? (
					<span className="mr-auto text-xs text-secondary dark:text-slate-400">
						{missing}
					</span>
				) : null}
				{realProvider && !off ? (
					<Button
						theme={ButtonTheme.Outline}
						size={Size.REGULAR}
						type="button"
						disabled={busy !== null || missing !== null}
						onClick={() => void runTest()}
					>
						{busy === 'test' ? 'Testing…' : 'Test'}
					</Button>
				) : null}
				<Button
					theme={ButtonTheme.Primary}
					size={Size.REGULAR}
					type="button"
					disabled={busy !== null || (provider !== SAME_AS_CHAT && missing !== null)}
					onClick={() => void save()}
				>
					{busy === 'save' ? 'Saving…' : 'Save'}
				</Button>
			</footer>
		</section>
	);
};
