// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import type { ReactNode } from 'react';
import type { TableRangeMeta } from '@/types/table';

type PaginationProps = {
	/** 1-based current page. */
	page: number;
	pageSize: number;
	totalItems: number;
	onPageChange: (page: number) => void;
	rangeTextFormatFn: (meta: TableRangeMeta) => ReactNode;
	className?: string;
};

/** Page numbers to show: the ends, the current page and its neighbours, gaps as null. */
const pageWindow = (page: number, pageCount: number): Array<number | null> => {
	const wanted = new Set([1, pageCount, page - 1, page, page + 1]);
	const pages = [...wanted].filter((p) => p >= 1 && p <= pageCount).sort((a, b) => a - b);
	const out: Array<number | null> = [];
	pages.forEach((p, index) => {
		if (index > 0 && p - pages[index - 1] > 1) out.push(null);
		out.push(p);
	});
	return out;
};

const arrowClass =
	'inline-flex h-8 w-8 items-center justify-center rounded-full text-body transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-30 dark:text-slate-300 dark:hover:bg-slate-800';

const Chevron = ({ flip = false }: { flip?: boolean }) => (
	<svg
		viewBox="0 0 16 16"
		aria-hidden
		className={`h-4 w-4 fill-current ${flip ? 'rotate-180' : ''}`}
	>
		<path d="M6.22 4.22a.75.75 0 011.06 0l3.25 3.25a.75.75 0 010 1.06l-3.25 3.25a.75.75 0 01-1.06-1.06L8.94 8 6.22 5.28a.75.75 0 010-1.06z" />
	</svg>
);

export const Pagination = ({
	page,
	pageSize,
	totalItems,
	onPageChange,
	rangeTextFormatFn,
	className = '',
}: PaginationProps) => {
	const pageCount = Math.max(1, Math.ceil(totalItems / Math.max(1, pageSize)));
	const current = Math.min(Math.max(1, page), pageCount);
	const firstItemIndex = totalItems === 0 ? 0 : (current - 1) * pageSize + 1;
	const lastItemIndex = Math.min(current * pageSize, totalItems);

	return (
		<nav
			aria-label="Pagination"
			className={`flex items-center gap-3 text-sm text-body dark:text-slate-400 ${className}`}
		>
			<div className="flex items-center gap-1">
				<button
					type="button"
					aria-label="Previous page"
					className={arrowClass}
					disabled={current <= 1}
					onClick={() => onPageChange(current - 1)}
				>
					<Chevron flip />
				</button>
				{pageWindow(current, pageCount).map((p, index) =>
					p == null ? (
						<span key={`gap-${index}`} className="px-1 text-secondary">
							…
						</span>
					) : (
						<button
							key={p}
							type="button"
							aria-current={p === current ? 'page' : undefined}
							onClick={() => onPageChange(p)}
							className={`inline-flex h-8 min-w-8 items-center justify-center rounded-full px-2 text-sm font-medium transition-colors ${
								p === current
									? 'bg-brand/15 text-brand-strong dark:text-brand-light'
									: 'hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
							}`}
						>
							{p}
						</button>
					),
				)}
				<button
					type="button"
					aria-label="Next page"
					className={arrowClass}
					disabled={current >= pageCount}
					onClick={() => onPageChange(current + 1)}
				>
					<Chevron />
				</button>
			</div>
			<span className="whitespace-nowrap">
				{rangeTextFormatFn({ firstItemIndex, lastItemIndex, totalItems })}
			</span>
		</nav>
	);
};
