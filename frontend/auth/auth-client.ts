// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { createAuthClient } from 'better-auth/react';
import { adminClient } from 'better-auth/client/plugins';
import { oauthProviderClient } from '@better-auth/oauth-provider/client';
import { ac, roles } from '@/auth/auth-access';

export const authClient = createAuthClient({
	plugins: [adminClient({ ac, roles }), oauthProviderClient()],
});

export const { signIn, signOut, useSession } = authClient;
