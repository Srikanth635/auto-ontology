// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { route } from '@/lib/server/route';
import { proxyToBackend } from '@/lib/server/proxy-backend';

// rulesApi.update — rename a rule.
//
// The identity goes with it, as it does with the create, but for the other
// column: `created_by` is left alone so the rule stays attributed to whoever
// saved it, and `modified_by` records who renamed it — which is what the
// information card reads to say who last edited the rule.
export const PATCH = route((req, { user }) => proxyToBackend(req, { userId: user.id }));

// rulesApi.delete — remove a rule, and with it the tags it applied unless
// `?keep_tags=true` says to leave them.
//
// No identity forwarded: nothing survives the delete to record an actor on.
export const DELETE = route((req) => proxyToBackend(req));
