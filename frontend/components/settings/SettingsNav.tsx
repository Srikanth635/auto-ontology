// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { SETTINGS_TABS, isActivePath, isDeveloperPath } from '@/constants/navigation';

export type SettingsNavProps = {
	/**
	 * Connections come from the CONNECTION_STRINGS env var, so they are fixed by
	 * config and the tab is dropped. Resolved by the server layout rather
	 * than fetched here: a client-side lookup rendered the link for as long as
	 * the request took, then took it away again.
	 */
	connectionsEnvManaged: boolean;
};

const tabClassName = (selected: boolean) =>
	`relative flex h-10 items-center px-3 text-sm no-underline transition-colors ${
		selected
			? 'font-medium text-heading after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:bg-brand dark:text-slate-100'
			: 'text-secondary hover:text-heading dark:text-slate-400 dark:hover:text-slate-200'
	}`;

export const SettingsNav = ({ connectionsEnvManaged }: SettingsNavProps) => {
	const pathname = usePathname();

	// The advanced sections are reached from the Developer menu and say where
	// they are in the breadcrumbs, so the everyday tabs stay out of their way.
	if (isDeveloperPath(pathname)) return null;

	const tabs = SETTINGS_TABS.filter(
		(tab) => !(connectionsEnvManaged && tab.href === '/settings/connections'),
	);

	return (
		<nav
			className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-slate-200 px-4 dark:border-slate-800"
			aria-label="Settings sections"
		>
			{tabs.map((tab) => (
				<Link
					key={tab.href}
					href={tab.href}
					className={tabClassName(isActivePath(pathname, tab.href))}
				>
					{tab.label}
				</Link>
			))}
		</nav>
	);
};
