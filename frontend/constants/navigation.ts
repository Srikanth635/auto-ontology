// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { NavLink } from '@/types/navigation';

/**
 * Where the app's pages are listed. Every route still exists wherever it is
 * listed here: moving a page between these arrays changes which menu shows it,
 * never whether it works.
 */

/** The tabs along the top bar. */
export const PRIMARY_NAV: NavLink[] = [
	{ label: 'Chat', href: '/chat' },
	{ label: 'Terms', href: '/terms' },
	{ label: 'Data', href: '/data' },
	{ label: 'NEEMs', href: '/neems' },
	{ label: 'Settings', href: '/settings' },
];

/** The Settings sub-tabs; everything else under /settings is in `DEVELOPER_NAV`. */
export const SETTINGS_TABS: NavLink[] = [
	{ label: 'Connections', href: '/settings/connections' },
	{ label: 'Models', href: '/settings/models' },
	{ label: 'Semantic Compilation', href: '/settings/semantic-compilation' },
];

/** Pages for working on the semantic layer itself, in the Developer menu. */
export const DEVELOPER_PAGES: NavLink[] = [
	{ label: 'Discovery', href: '/discovery' },
	{ label: 'Analysis', href: '/analysis' },
	{ label: 'Exploration', href: '/exploration' },
	{ label: 'Analytics', href: '/analytics' },
];

/** Advanced settings, in the Developer menu. */
export const DEVELOPER_SETTINGS: NavLink[] = [
	{ label: 'Tags', href: '/settings/tags' },
	{ label: 'Rules', href: '/settings/rules' },
	{ label: 'PII Settings', href: '/settings/pii' },
	{ label: 'Semantic Input', href: '/settings/semantic-input' },
	{ label: 'Agent Settings', href: '/settings/agent-settings' },
	{ label: 'Import / Export', href: '/settings/import-export' },
];

export const isActivePath = (pathname: string, href: string): boolean =>
	pathname === href || pathname.startsWith(`${href}/`);

export const isDeveloperPath = (pathname: string): boolean =>
	[...DEVELOPER_PAGES, ...DEVELOPER_SETTINGS].some((item) => isActivePath(pathname, item.href));
