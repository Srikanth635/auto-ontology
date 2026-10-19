// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { type ReactNode } from 'react';
import { SettingsNav } from '@/components/settings/SettingsNav';

type SettingsPanelLayoutProps = {
	children: ReactNode;
	/** Passed straight to the nav, which drops Connections when it is set. */
	connectionsEnvManaged: boolean;
};

export const SettingsPanelLayout = ({
	children,
	connectionsEnvManaged,
}: SettingsPanelLayoutProps) => (
	<div className="flex h-full w-full flex-col bg-white dark:bg-slate-950">
		<SettingsNav connectionsEnvManaged={connectionsEnvManaged} />
		<div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
	</div>
);
