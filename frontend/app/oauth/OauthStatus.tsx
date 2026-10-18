// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const OauthStatus = ({ title, children }: { title: string; children: React.ReactNode }) => (
	<div className="flex w-full max-w-md flex-col gap-3 text-center">
		<h1 className="text-xl font-semibold text-heading dark:text-slate-100">{title}</h1>
		<p className="text-sm text-body dark:text-slate-400">{children}</p>
	</div>
);
