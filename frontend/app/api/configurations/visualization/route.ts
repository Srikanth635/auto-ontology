// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NextResponse } from 'next/server';
import { getPrisma } from '@/lib/prisma';
import { VISUALIZATION_ENABLED_KEY, isVisualizationEnabled } from '@/lib/configurations';
import { route } from '@/lib/server/route';

// Report whether the instance-wide "Visualize SQL Results" setting is on.
//
// The flag lives under Settings > Agent Settings, stored in the
// `configurations` key/value table. The chat proxy route resolves the value per
// request, so a client cannot override it.
export const GET = route(async () => {
	return NextResponse.json({ enabled: await isVisualizationEnabled() });
});

// Turn the instance-wide "Visualize SQL Results" setting on or off.
//
// Chat resolves the value per request, so the change takes effect on the next
// question without a client reload. It gates chart *generation* only — the
// result table still renders when it is off.
export const PUT = route(async (req) => {
	const prisma = getPrisma();
	const body = await req.json();
	const enabled = body.enabled === true;
	const value = enabled ? 'true' : 'false';

	await prisma.configuration.upsert({
		where: { key: VISUALIZATION_ENABLED_KEY },
		create: { key: VISUALIZATION_ENABLED_KEY, value },
		update: { value },
	});

	return NextResponse.json({ enabled });
});
