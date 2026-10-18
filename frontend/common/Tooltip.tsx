// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

const OPEN_DELAY_MS = 400;
const GAP_PX = 6;

type TooltipProps = {
	content: ReactNode;
	children: ReactNode;
	className?: string;
};

type Position = { top: number; left: number };

/**
 * A hover/focus tooltip shown below its trigger, start-aligned.
 *
 * The wrapper is `display: contents`, so it adds nothing to layout; the
 * position is taken from the first element it wraps. The bubble is portalled
 * to `document.body` so overflow-clipped containers cannot cut it off.
 */
export const Tooltip = ({ content, children, className = '' }: TooltipProps) => {
	const wrapperRef = useRef<HTMLSpanElement | null>(null);
	const timer = useRef<number | null>(null);
	const [position, setPosition] = useState<Position | null>(null);

	const clear = () => {
		if (timer.current != null) window.clearTimeout(timer.current);
		timer.current = null;
	};

	const open = () => {
		clear();
		timer.current = window.setTimeout(() => {
			const target = wrapperRef.current?.firstElementChild;
			if (!target) return;
			const rect = target.getBoundingClientRect();
			setPosition({ top: rect.bottom + GAP_PX, left: rect.left });
		}, OPEN_DELAY_MS);
	};

	const close = () => {
		clear();
		setPosition(null);
	};

	useEffect(() => clear, []);

	useEffect(() => {
		if (position == null) return;
		// A tooltip that stays put while its trigger scrolls away looks broken.
		const onScroll = () => {
			if (timer.current != null) window.clearTimeout(timer.current);
			timer.current = null;
			setPosition(null);
		};
		window.addEventListener('scroll', onScroll, true);
		return () => window.removeEventListener('scroll', onScroll, true);
	}, [position]);

	return (
		<span
			ref={wrapperRef}
			className="contents"
			onPointerEnter={open}
			onPointerLeave={close}
			onFocus={open}
			onBlur={close}
		>
			{children}
			{position != null && typeof document !== 'undefined'
				? createPortal(
						// Inline style only for the coordinates, which are measured at runtime
						// and so cannot be a class.
						<span
							role="tooltip"
							style={{ position: 'fixed', top: position.top, left: position.left }}
							className={className}
						>
							{content}
						</span>,
						document.body,
					)
				: null}
		</span>
	);
};
