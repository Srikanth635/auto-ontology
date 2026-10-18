// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';

const HTTP_METHODS = 'GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS';

// Every API route handler is wrapped in `route()` from `@/lib/server/route` —
// never a bare handler — so each one receives the local user the same way, and
// the OpenAPI generator can read every export as `export const METHOD = …`.
const routeWrapperCoverage = {
	files: ['app/api/**/route.ts'],
	rules: {
		'no-restricted-syntax': [
			'error',
			{
				selector: `ExportNamedDeclaration > FunctionDeclaration[id.name=/^(${HTTP_METHODS})$/]`,
				message:
					'API route handlers must be wrapped: `export const GET = route(fn)`, not a bare `export async function GET`.',
			},
			{
				selector: `ExportNamedDeclaration > VariableDeclaration > VariableDeclarator[id.name=/^(${HTTP_METHODS})$/]:not([init.callee.name='route'])`,
				message:
					'API route handlers must be wrapped in route(...) from @/lib/server/route.',
			},
		],
	},
};

const eslintConfig = defineConfig([
	...nextVitals,
	...nextTs,
	routeWrapperCoverage,
	globalIgnores(['.next/**', 'out/**', 'build/**', 'next-env.d.ts', '.cache/**']),
]);

export default eslintConfig;
