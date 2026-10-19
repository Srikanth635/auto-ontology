// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import {
	HydrationBoundary,
	QueryClient,
	defaultShouldDehydrateQuery,
	dehydrate,
	type DehydratedState,
} from '@tanstack/react-query';
import { TopNav } from '@/common/TopNav';
import { AppTopBar } from '@/common/AppTopBar';
import { BreadcrumbProvider } from '@/contexts/BreadcrumbContext';
import { QueryProvider } from '@/contexts/QueryProvider';
import { connectionQueries } from '@/lib/queries/connections';
import { tagQueries } from '@/lib/queries/tags';
import './globals.css';

const geistSans = Geist({
	variable: '--font-geist-sans',
	subsets: ['latin'],
});

const geistMono = Geist_Mono({
	variable: '--font-geist-mono',
	subsets: ['latin'],
});

// Every page reads live data from the backend (the shared lists below, and each
// page's own), so nothing is prerendered at build time, when no backend runs.
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
	title: {
		default: 'neemontology',
		template: 'neemontology - %s',
	},
	description: 'neemontology — a semantic layer and natural-language querying for your databases',
	icons: {
		icon: '/favicon.svg',
	},
};

/**
 * The reads the whole app shares, started here so they arrive with the page
 * rather than after it: this layout survives every client navigation, so one
 * pass covers the session, not each route inside it.
 *
 * Both are read here rather than in the section that happens to show
 * them: they describe the deployment rather than a page, and a picker that
 * has to wait for its own read is the thing this exists to remove. The cost
 * is two internal reads per *full* page load — client navigations reuse
 * them — and neither is awaited.
 *
 * That is also why the dehydrated state has to carry the pending queries
 * themselves, dehydrated alongside what `defaultShouldDehydrateQuery` already
 * keeps: the markup is not held back for lists the first screen may not even
 * show, and the browser subscribes to reads already in flight instead of
 * starting its own.
 */
const prefetchSharedData = (): DehydratedState => {
	const queryClient = new QueryClient();
	void queryClient.prefetchQuery(tagQueries.vocabulary());
	void queryClient.prefetchQuery(connectionQueries.list());
	return dehydrate(queryClient, {
		shouldDehydrateQuery: (query) =>
			defaultShouldDehydrateQuery(query) || query.state.status === 'pending',
	});
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	// Optional: set APP_VERSION to show a version in the user menu.
	const appVersion = process.env.APP_VERSION;

	return (
		<html
			lang="en"
			className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
		>
			<body className="flex h-full flex-col bg-canvas text-heading dark:text-slate-100">
				<QueryProvider>
					<HydrationBoundary state={prefetchSharedData()}>
						<BreadcrumbProvider>
							<TopNav version={appVersion} />
							<AppTopBar />
							<div className="min-h-0 min-w-0 flex-1">{children}</div>
						</BreadcrumbProvider>
					</HydrationBoundary>
				</QueryProvider>
			</body>
		</html>
	);
}
