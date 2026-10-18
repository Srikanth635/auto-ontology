// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import path from 'node:path';
import dotenv from 'dotenv';
import type { NextConfig } from 'next';

dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

// NOTE: there are intentionally no `rewrites()`. Every /api/* path is served by
// a route handler under app/api/** that forwards to the backend (see
// lib/server/proxy-backend.ts), which is also what the OpenAPI generator reads.
const nextConfig: NextConfig = {
	output: process.env.NEXT_OUTPUT === 'standalone' ? 'standalone' : undefined,
	outputFileTracingRoot: path.resolve(__dirname, '..'),
	turbopack: {
		rules: {
			'*.svg': {
				loaders: [{ loader: '@svgr/webpack', options: { svgo: false } }],
				as: '*.js',
			},
		},
	},
};

export default nextConfig;
