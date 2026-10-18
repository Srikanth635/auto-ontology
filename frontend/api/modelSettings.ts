// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { requests } from './requests';
import type {
	ModelRoleId,
	ModelSettingInput,
	ModelSettingSaveResult,
	ModelSettingsPayload,
	ModelTestResult,
	ReembedStatus,
} from '@/types/modelSettings';

const rolePath = (role: ModelRoleId) => `model-settings/${encodeURIComponent(role)}`;

export const modelSettingsApi = {
	/** Every role's effective model, what each role may use, and the re-embed status. */
	getAll: () => requests.get<ModelSettingsPayload>('model-settings'),

	/** Save a role. Changing the embedding model starts a background re-embed. */
	save: (role: ModelRoleId, input: ModelSettingInput) =>
		requests.put<ModelSettingSaveResult>(rolePath(role), input),

	/** Forget a role's saved setting, so it falls back to the environment (or the chat model). */
	reset: (role: ModelRoleId) => requests.delete<ModelSettingSaveResult>(rolePath(role)),

	/** One small real call with an unsaved setting. */
	test: (role: ModelRoleId, input: ModelSettingInput) =>
		requests.post<ModelTestResult>(`${rolePath(role)}/verify`, input),

	/** The model ids the provider offers, for the model picker. */
	listModels: (role: ModelRoleId, input: ModelSettingInput) =>
		requests.post<{ models: string[] }>(`${rolePath(role)}/models`, input),

	reembedStatus: () => requests.get<ReembedStatus>('model-settings/reembed'),

	/** Rebuild every stored vector with the current embedding model. */
	reembed: () => requests.post<{ status: string }>('model-settings/reembed'),
};
