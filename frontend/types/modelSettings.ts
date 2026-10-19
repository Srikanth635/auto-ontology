// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** A model role: what a model is configured to do. */
export type ModelRoleId = 'chat' | 'fast_chat' | 'embedding' | 'rerank';

/** Who serves a role. Which provider fits which role comes from the backend catalog. */
export type ModelProviderId =
	| 'openai'
	| 'anthropic'
	| 'nvidia'
	| 'openai_compatible'
	| 'rerank_api'
	| 'none';

/** Where a role's effective value comes from. */
export type ModelSettingSource = 'settings' | 'environment' | 'chat' | 'unset';

/** One role's effective model. The API key itself is never sent to the browser. */
export type ModelSetting = {
	role: ModelRoleId;
	provider: ModelProviderId;
	model: string;
	base_url: string;
	dimensions: number | null;
	has_api_key: boolean;
	configured: boolean;
	source: ModelSettingSource;
};

export type ModelProviderInfo = {
	label: string;
	default_base_url: string;
	key_required: boolean;
};

export type ModelRoleInfo = {
	label: string;
	providers: ModelProviderId[];
};

export type ReembedStatus = {
	running: boolean;
	last_started_at: string | null;
	last_finished_at: string | null;
	last_error: string | null;
};

export type ModelSettingsPayload = {
	data: ModelSetting[];
	roles: Record<ModelRoleId, ModelRoleInfo>;
	providers: Record<ModelProviderId, ModelProviderInfo>;
	reembed: ReembedStatus | null;
};

/**
 * What a role is set to. `api_key` omitted keeps the stored key (same provider
 * only); an empty string removes it.
 */
export type ModelSettingInput = {
	provider: ModelProviderId;
	model: string;
	base_url: string;
	api_key?: string;
	dimensions: number | null;
};

export type ModelSettingSaveResult = {
	data: ModelSetting;
	reembed_triggered: boolean;
};

export type ModelTestResult = {
	ok: boolean;
	detail: string;
	dimensions?: number | null;
};
