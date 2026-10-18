// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { authClient } from '@/auth/auth-client';

export const authApi = {
	/** Email/password sign-in. */
	signInWithPassword: (email: string, password: string) =>
		authClient.signIn.email({ email, password }),
};
