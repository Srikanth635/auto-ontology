// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Wrapper for API route handlers. There is no sign-in: this is a local, single-
// user setup, so every request acts as the one local user. The wrapper exists
// so handlers that record who did something (a conversation's owner, a tag's
// author) receive that identity the same way everywhere.
//
//   export const GET = route(async (req) => { ... });
//   export const DELETE = route<{ params: Promise<{ id: string }> }>(async (req, { params, user }) => { ... });

/** The id every conversation, tag and setting is recorded under. */
export const LOCAL_USER_ID = 'local';

export type LocalUser = { id: string };

const LOCAL_USER: LocalUser = { id: LOCAL_USER_ID };

// Next requires every route handler, even a static one, to accept a context
// with `params`; a catch-all segment resolves to string[], so admit both.
type RouteContext = { params: Promise<Record<string, string | string[]>> };

type Handler<C extends RouteContext> = (
	req: Request,
	ctx: C & { user: LocalUser },
) => Response | Promise<Response>;

export function route<C extends RouteContext = RouteContext>(handler: Handler<C>) {
	return (req: Request, ctx: C = {} as C): Response | Promise<Response> =>
		handler(req, { ...ctx, user: LOCAL_USER });
}
