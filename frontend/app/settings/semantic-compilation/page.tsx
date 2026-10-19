// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { connectionsApi } from '@/api/connections';
import { datasources } from '@/api/datasources';
import { getPrisma } from '@/lib/prisma';
import { DISTINCT_VALUE_PROBING_ENABLED_KEY, readOptOutFlag } from '@/lib/configurations';
import { readConnectionsEnvSource } from '@/lib/server/connections';
import { SemanticCompilationForm } from './SemanticCompilationForm';

const CONFIG_KEY = 'semantic_compilation_enabled';
const PROBING_CONFIG_KEY = DISTINCT_VALUE_PROBING_ENABLED_KEY;

const SemanticCompilationPage = async () => {
	// Fetch on the server so the toggles (and the connected-database hint)
	// render in the correct state on first paint, with no client-side flash.
	const [row, probingRow, connections, isEnvSource, catalog] = await Promise.all([
		getPrisma().configuration.findUnique({ where: { key: CONFIG_KEY } }),
		getPrisma().configuration.findUnique({ where: { key: PROBING_CONFIG_KEY } }),
		connectionsApi.getAll(),
		readConnectionsEnvSource(),
		datasources.getDBs(),
	]);
	// `connections.count` only reflects UI-managed connections (stored on the
	// catalog database row) — it's always 0 when connections instead
	// come from CONNECTION_STRINGS, since that path never writes either. Treat
	// env-managed mode as "databases connected" too, otherwise this would tell
	// an operator to "connect a data source" they already configured.
	// The merged NEEM database is neither: it comes from the NEEM folder, so it
	// is only visible as a database the catalog already holds.
	const hasDatabases =
		(!connections.error && connections.count > 0) ||
		isEnvSource === true ||
		(!catalog.error && catalog.count > 0);
	return (
		<SemanticCompilationForm
			initialEnabled={row?.value === 'true'}
			// Opt-out, so absent reads as on — see the route for why the two
			// flags default in opposite directions. Canonicalized through the
			// shared reader so this first paint cannot disagree with the
			// ingestion service about what the stored value means.
			initialProbingEnabled={readOptOutFlag(probingRow?.value)}
			hasDatabases={hasDatabases}
		/>
	);
};

export default SemanticCompilationPage;
