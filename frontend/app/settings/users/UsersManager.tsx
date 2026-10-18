// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSession } from '@/auth/auth-client';
import { Role } from '@/enums/auth';
import { usersApi } from '@/api/users';
import { Button } from '@/common/Button';
import { Icon, IconName } from '@/common/icons';
import { Size, ButtonTheme } from '@/enums/button';
import { ToastVariant } from '@/enums/toast';
import { Table } from '@/common/Table';
import { SkeletonTable } from '@/common/Skeleton';
import { Toast } from '@/common/Toast';
import { PopoverMenu } from '@/common/PopoverMenu';
import { ConfirmModal } from '@/common/modal';
import type { TableColumn } from '@/types/table';
import type { UpdateUserInput, User } from '@/types/auth';
import { invalidateOwners } from '@/lib/queries/owners';
import { GroupsSection } from './GroupsSection';
import { EditUserModal } from './EditUserModal';

const actionErrorMessage = (error: unknown, fallback: string): string => {
	if (typeof error === 'object' && error && 'message' in error) {
		const message = (error as { message?: string }).message;
		if (message) return message;
	}
	return fallback;
};

export const UsersManager = () => {
	const queryClient = useQueryClient();
	const { data: session } = useSession();
	const [users, setUsers] = useState<User[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [busyId, setBusyId] = useState<string | null>(null);
	const [groupsRefresh, setGroupsRefresh] = useState(0);
	const [editingUser, setEditingUser] = useState<User | null>(null);
	const [editing, setEditing] = useState(false);
	const [editError, setEditError] = useState<string | null>(null);
	const [pendingDeleteUser, setPendingDeleteUser] = useState<User | null>(null);

	const currentUserId = session?.user.id;
	const adminCount = users.filter((user) => user.role === Role.Admin).length;
	const editingRoleLockedReason =
		editingUser?.id === currentUserId
			? 'You cannot change your own role.'
			: editingUser?.role === Role.Admin && adminCount <= 1
				? 'The last admin cannot be made a viewer.'
				: null;

	useEffect(() => {
		void usersApi.list().then((listed) => {
			setUsers(listed.users);
			setError(listed.error ?? null);
			setLoading(false);
		});
	}, []);

	const runAction = async (id: string, action: () => Promise<{ error?: unknown }>) => {
		setBusyId(id);
		setError(null);
		const actionResult = await action();
		if (actionResult.error) {
			setError(actionErrorMessage(actionResult.error, 'Action failed.'));
		} else {
			await invalidateOwners(queryClient);
		}
		const listed = await usersApi.list();
		setUsers(listed.users);
		if (listed.error) setError(listed.error);
		setGroupsRefresh((current) => current + 1);
		setBusyId(null);
	};

	const editUser = async (user: User, input: UpdateUserInput) => {
		if (user.id === currentUserId && input.role !== user.role) {
			setEditError('You cannot change your own role.');
			return;
		}
		if (user.role === Role.Admin && adminCount <= 1 && input.role !== Role.Admin) {
			setEditError('The last admin cannot be made a viewer.');
			return;
		}
		setEditing(true);
		setEditError(null);
		const result = await usersApi.update(user.id, input);
		if (result.error) {
			setEditError(actionErrorMessage(result.error, 'Failed to update the user.'));
			setEditing(false);
			return;
		}
		await invalidateOwners(queryClient);
		const listed = await usersApi.list();
		if (listed.error) {
			setError(listed.error);
		} else {
			setUsers(listed.users);
		}
		setEditingUser(null);
		setEditing(false);
	};

	const deleteUser = (user: User) => {
		setPendingDeleteUser(user);
	};

	const confirmDeleteUser = async () => {
		if (!pendingDeleteUser) return;
		await runAction(pendingDeleteUser.id, () => usersApi.remove(pendingDeleteUser.id));
		setPendingDeleteUser(null);
	};

	const columns: TableColumn<User>[] = [
		{
			key: 'user',
			header: 'User',
			cell: (user) => (
				<div>
					<div className="font-medium">{user.name || '—'}</div>
					<div className="text-xs text-secondary">{user.email}</div>
				</div>
			),
		},
		{
			key: 'role',
			header: 'Role',
			width: 'w-32',
			nowrap: true,
			cell: (user) => (user.role === Role.Admin ? 'Admin' : 'Viewer'),
		},
		{
			key: 'actions',
			header: 'Actions',
			width: 'w-16',
			nowrap: true,
			headerClassName: 'text-right',
			cell: (user) => {
				const isAdmin = user.role === Role.Admin;
				// Never let the last admin be demoted or deleted.
				const isLastAdmin = isAdmin && adminCount <= 1;
				const busy = busyId === user.id;
				return (
					<div className="flex justify-end">
						<PopoverMenu
							items={[
								{
									label: 'Edit',
									icon: <Icon name={IconName.Pencil} className="h-3.5 w-3.5" />,
									onClick: () => {
										setEditError(null);
										setEditingUser(user);
									},
								},
								{
									label: 'Delete',
									icon: <Icon name={IconName.Trash} className="h-3.5 w-3.5" />,
									onClick: () => void deleteUser(user),
									disabled: isLastAdmin,
									danger: true,
								},
							]}
							trigger={({ toggle }) => (
								<Button
									theme={ButtonTheme.IconNeutral}
									size={Size.SMALL}
									iconOnly
									type="button"
									disabled={busy}
									onClick={toggle}
									aria-label={`Actions for ${user.name || user.email}`}
								>
									<Icon name={IconName.DotsVertical} className="h-4 w-4" />
								</Button>
							)}
						/>
					</div>
				);
			},
		},
	];

	return (
		<div className="h-full overflow-auto p-6">
			<div className="mx-auto max-w-6xl">
				<div className="mb-4">
					<h1 className="mb-1 text-lg font-semibold text-heading dark:text-zinc-100">
						Users
					</h1>
					<p className="text-xs text-secondary">
						Admins manage users; viewers can read the other pages and use chat.
					</p>
				</div>

				{loading ? (
					<div role="status" aria-label="Loading users">
						<SkeletonTable columns={3} rows={8} />
					</div>
				) : (
					<Table
						columns={columns}
						rows={users}
						rowKey={(user) => user.id}
						layout="auto"
						emptyMessage="No Users Found"
					/>
				)}

				<GroupsSection users={users} usersLoading={loading} refreshToken={groupsRefresh} />
			</div>

			{editingUser ? (
				<EditUserModal
					user={editingUser}
					roleLockedReason={editingRoleLockedReason}
					submitting={editing}
					error={editError}
					onClose={() => {
						if (!editing) setEditingUser(null);
					}}
					onEdit={(input) => {
						void editUser(editingUser, input);
					}}
				/>
			) : null}

			<ConfirmModal
				open={pendingDeleteUser !== null}
				title="Delete User"
				message={
					pendingDeleteUser == null
						? ''
						: `Delete user "${pendingDeleteUser.name || pendingDeleteUser.email}"? This permanently removes the account and its data.`
				}
				confirmLabel="Delete"
				onConfirm={confirmDeleteUser}
				onCancel={() => {
					if (pendingDeleteUser == null || busyId !== pendingDeleteUser.id) {
						setPendingDeleteUser(null);
					}
				}}
				confirming={pendingDeleteUser != null && busyId === pendingDeleteUser.id}
			/>

			<Toast
				open={error !== null}
				message={error ?? ''}
				variant={ToastVariant.Error}
				onClose={() => setError(null)}
			/>
		</div>
	);
};
