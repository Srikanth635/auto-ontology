// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { forwardRef, type ButtonHTMLAttributes } from 'react';

import { ButtonTheme, Size } from '@/enums/button';

const themeClasses: Record<ButtonTheme, string> = {
	[ButtonTheme.Primary]:
		'border border-transparent bg-brand text-white hover:bg-brand-strong disabled:bg-slate-100 disabled:text-disabled dark:disabled:bg-slate-800 dark:disabled:text-slate-500',
	[ButtonTheme.Secondary]:
		'border border-slate-300 bg-white text-body hover:border-brand hover:bg-brand/10 hover:text-brand-strong dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-brand/20 dark:hover:text-brand-light disabled:border-transparent disabled:bg-slate-100 disabled:text-disabled dark:disabled:bg-slate-800 dark:disabled:text-slate-500',
	[ButtonTheme.Outline]:
		'border border-brand bg-white text-brand-strong hover:bg-brand-strong hover:text-white dark:bg-slate-900 dark:hover:bg-brand-strong disabled:border-slate-300 disabled:bg-transparent disabled:text-disabled dark:disabled:border-slate-600 dark:disabled:text-slate-500',
	[ButtonTheme.Danger]:
		'border border-transparent bg-red-600 text-white hover:bg-red-700 disabled:bg-slate-100 disabled:text-disabled dark:disabled:bg-slate-800 dark:disabled:text-slate-500',
	[ButtonTheme.DangerOutline]:
		'border border-red-500 bg-white text-red-600 hover:bg-red-600 hover:text-white dark:border-red-500 dark:bg-slate-900 dark:text-red-400 dark:hover:bg-red-600 disabled:border-slate-300 disabled:bg-white disabled:text-disabled dark:disabled:border-slate-600 dark:disabled:bg-slate-900 dark:disabled:text-slate-500',
	[ButtonTheme.DangerSubtle]:
		'border border-red-300 bg-white text-red-600 hover:bg-red-50 dark:border-red-800 dark:bg-slate-900 dark:text-red-400 dark:hover:bg-red-950/30 disabled:border-slate-300 disabled:bg-white disabled:text-disabled dark:disabled:border-slate-600 dark:disabled:bg-slate-900 dark:disabled:text-slate-500',
	[ButtonTheme.Minimal]:
		'border border-transparent bg-transparent text-body hover:bg-brand/10 hover:text-brand-strong dark:text-slate-300 dark:hover:bg-brand/20 dark:hover:text-brand-light disabled:text-disabled disabled:hover:bg-transparent dark:disabled:text-slate-500',
	[ButtonTheme.Icon]:
		'border border-transparent bg-transparent text-secondary hover:bg-brand/10 hover:text-brand-strong dark:hover:bg-brand/20 dark:hover:text-brand-light disabled:text-disabled disabled:hover:bg-transparent dark:disabled:text-slate-600',
	[ButtonTheme.IconNeutral]:
		'border border-transparent bg-transparent text-secondary hover:bg-slate-100 hover:text-body dark:hover:bg-slate-700 dark:hover:text-slate-200 disabled:text-disabled disabled:hover:bg-transparent dark:disabled:text-slate-600',
	[ButtonTheme.IconDanger]:
		'border border-transparent bg-transparent text-secondary hover:text-red-600 dark:text-slate-400 dark:hover:text-red-400 disabled:text-disabled disabled:hover:bg-transparent dark:disabled:text-slate-600',
	[ButtonTheme.Soft]:
		'border border-brand/40 bg-white text-brand-strong hover:bg-brand/10 dark:border-brand/40 dark:bg-slate-900 dark:text-brand-light dark:hover:bg-brand/15 disabled:border-slate-300 disabled:bg-white disabled:text-disabled dark:disabled:border-slate-600 dark:disabled:bg-slate-900 dark:disabled:text-slate-500',
};

const sizeClasses: Record<Size, string> = {
	[Size.SMALL]: 'h-[26px] text-xs',
	[Size.REGULAR]: 'h-9 text-sm',
	[Size.LARGE]: 'h-10 text-sm',
};

const radiusClasses: Record<Size, string> = {
	[Size.SMALL]: 'rounded-md',
	[Size.REGULAR]: 'rounded-lg',
	[Size.LARGE]: 'rounded-xl',
};

const iconOnlySizeClasses: Record<Size, string> = {
	[Size.SMALL]: 'w-[26px]',
	[Size.REGULAR]: 'w-9',
	[Size.LARGE]: 'w-10',
};

export type IconPosition = 'left' | 'right';

const setPaddingClasses = (size: Size, noPadding: boolean): string => {
	if (noPadding) return 'p-0';
	return size === Size.SMALL ? 'px-2' : 'px-4';
};

export type ButtonProps = {
	theme?: ButtonTheme;
	size?: Size;
	loading?: boolean;
	iconPosition?: IconPosition;
	iconOnly?: boolean;
	noPadding?: boolean;
	rounded?: boolean;
	full?: boolean;
	shadow?: boolean;
};

export const Button = forwardRef<
	HTMLButtonElement,
	ButtonProps & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'>
>(
	(
		{
			children,
			theme = ButtonTheme.Primary,
			size = Size.REGULAR,
			loading = false,
			iconPosition,
			iconOnly = false,
			noPadding = false,
			rounded = false,
			full = false,
			shadow = false,
			disabled = false,
			type = 'button',
			...props
		},
		ref,
	) => (
		<button
			{...props}
			ref={ref}
			type={type}
			disabled={disabled || loading}
			aria-busy={loading || undefined}
			className={[
				'inline-flex cursor-pointer items-center justify-center whitespace-nowrap font-medium transition-colors disabled:cursor-default disabled:opacity-100',
				themeClasses[theme],
				sizeClasses[size],
				rounded ? 'rounded-full' : radiusClasses[size],
				iconOnly ? iconOnlySizeClasses[size] : setPaddingClasses(size, noPadding),
				iconOnly && 'p-0',
				iconPosition && 'gap-1.5',
				full && 'w-full',
				shadow && 'shadow-sm',
			]
				.filter(Boolean)
				.join(' ')}
		>
			{children}
		</button>
	),
);

Button.displayName = 'Button';
