// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Metadata } from 'next';

export const metadata: Metadata = {
	title: 'NEEMs',
};

export default function NeemsLayout({ children }: { children: React.ReactNode }) {
	return children;
}
