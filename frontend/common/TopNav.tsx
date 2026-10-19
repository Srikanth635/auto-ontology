// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Icon, IconName } from '@/common/icons';
import { GlobalSearch } from '@/common/GlobalSearch';
import { Popover } from '@/common/Popover';
import {
	DEVELOPER_PAGES,
	DEVELOPER_SETTINGS,
	PRIMARY_NAV,
	isActivePath,
	isDeveloperPath,
} from '@/constants/navigation';
import type { NavLink } from '@/types/navigation';

const tabClassName = (active: boolean) =>
	`relative flex h-full items-center px-3 text-sm font-medium transition-colors ${
		active
			? 'text-heading after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:bg-brand dark:text-slate-100'
			: 'text-secondary hover:text-heading dark:text-slate-400 dark:hover:text-slate-200'
	}`;

const menuItemClassName = (active: boolean) =>
	`block rounded-md px-3 py-1.5 text-sm no-underline transition-colors ${
		active
			? 'bg-brand/15 font-medium text-heading dark:text-slate-100'
			: 'text-body hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60'
	}`;

const MenuSection = ({
	title,
	items,
	pathname,
	close,
}: {
	title: string;
	items: NavLink[];
	pathname: string;
	close: () => void;
}) => (
	<div className="px-1 py-1">
		<div className="px-3 pt-1 pb-1 text-xs font-medium tracking-wide text-secondary uppercase dark:text-slate-500">
			{title}
		</div>
		{items.map((item) => (
			<Link
				key={item.href}
				href={item.href}
				onClick={close}
				className={menuItemClassName(isActivePath(pathname, item.href))}
			>
				{item.label}
			</Link>
		))}
	</div>
);

const DeveloperMenu = ({ pathname }: { pathname: string }) => {
	const active = isDeveloperPath(pathname);

	return (
		<Popover
			panelClassName="w-56 py-1"
			trigger={({ open, toggle }) => (
				<button
					type="button"
					onClick={toggle}
					aria-haspopup="menu"
					aria-expanded={open}
					className={`flex h-8 items-center gap-1 rounded-lg px-2.5 text-sm font-medium transition-colors ${
						active || open
							? 'bg-slate-100 text-heading dark:bg-slate-800 dark:text-slate-100'
							: 'text-secondary hover:bg-slate-100 hover:text-heading dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
					}`}
				>
					Developer
					<svg
						viewBox="0 0 16 16"
						fill="none"
						aria-hidden="true"
						className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
					>
						<path
							d="M4 6l4 4 4-4"
							stroke="currentColor"
							strokeWidth="1.5"
							strokeLinecap="round"
							strokeLinejoin="round"
						/>
					</svg>
				</button>
			)}
		>
			{({ close }) => (
				<>
					<MenuSection
						title="Pages"
						items={DEVELOPER_PAGES}
						pathname={pathname}
						close={close}
					/>
					<div className="border-t border-slate-100 dark:border-slate-700" />
					<MenuSection
						title="Advanced settings"
						items={DEVELOPER_SETTINGS}
						pathname={pathname}
						close={close}
					/>
				</>
			)}
		</Popover>
	);
};

export const TopNav = ({ version }: { version?: string }) => {
	const pathname = usePathname();
	const developerPath = isDeveloperPath(pathname);

	return (
		<header className="flex h-12 shrink-0 items-center gap-6 border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-950">
			<Link href="/chat" aria-label="Home" className="flex shrink-0 items-center">
				<Icon name={IconName.AppLogo} className="h-5 w-5 text-brand" />
			</Link>
			<nav aria-label="Main" className="flex h-full items-center">
				{PRIMARY_NAV.map((item) => (
					<Link
						key={item.href}
						href={item.href}
						className={tabClassName(
							isActivePath(pathname, item.href) && !developerPath,
						)}
					>
						{item.label}
					</Link>
				))}
			</nav>
			<div className="ml-auto flex items-center gap-3">
				<GlobalSearch />
				<DeveloperMenu pathname={pathname} />
				{version ? (
					<span className="text-xs text-secondary dark:text-slate-500">v{version}</span>
				) : null}
			</div>
		</header>
	);
};
