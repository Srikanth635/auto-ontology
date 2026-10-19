// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { Breadcrumbs } from '@/common/Breadcrumbs';
import { useBreadcrumbs } from '@/contexts/BreadcrumbContext';

/**
 * The strip under the main navigation: where you are, and the current page's
 * own actions. The page links live in `TopNav`.
 */
export const AppTopBar = () => {
	const { items, rightSlot } = useBreadcrumbs();

	if (items.length === 0 && !rightSlot) return null;

	return (
		<div className="flex h-10 shrink-0 items-center border-b border-slate-200 bg-canvas px-4 dark:border-slate-800">
			<Breadcrumbs items={items} />
			{rightSlot ? <div className="ml-auto flex items-center gap-2">{rightSlot}</div> : null}
		</div>
	);
};
