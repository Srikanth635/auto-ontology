// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

'use client';

import { Button } from '@/common/Button';
import { Size, ButtonTheme } from '@/enums/button';
import { Icon, IconName } from '@/common/icons';
import { PopoverMenu } from '@/common/PopoverMenu';
import { Text } from '@/common/Text';
import { TextVariant } from '@/enums/text';
import type { Connection } from '@/types/connection';

export type ConnectionInfoCardProps = {
	connection: Connection;
	onEdit?: (connection: Connection) => void;
	onDelete?: (databaseName: string) => void;
	disabled?: boolean;
};

export const ConnectionInfoCard = ({
	connection,
	onEdit,
	onDelete,
	disabled = false,
}: ConnectionInfoCardProps) => {
	const menuItems = [
		...(onEdit == null
			? []
			: [
					{
						label: 'Edit',
						icon: <Icon name={IconName.Pencil} className="h-3.5 w-3.5" />,
						onClick: () => onEdit(connection),
					},
				]),
		...(onDelete == null
			? []
			: [
					{
						label: 'Remove',
						icon: <Icon name={IconName.Trash} className="h-3.5 w-3.5" />,
						onClick: () => onDelete(connection.database_name),
						danger: true,
					},
				]),
	];
	const menuDisabled = disabled || menuItems.length === 0;

	return (
		<article className="flex h-fit flex-col rounded-lg border border-zinc-200/90 bg-white shadow-sm dark:border-zinc-700/90 dark:bg-zinc-950">
			<header className="flex w-full items-center justify-between gap-2 px-4 py-5">
				<div className="flex min-w-0 items-center gap-1">
					<Icon
						name={IconName.Database}
						className="h-5 w-5 shrink-0 text-body dark:text-zinc-300"
					/>
					<Text
						as="h3"
						text={connection.database_name}
						variant={TextVariant.Subheading}
					/>
				</div>
				<div className="relative shrink-0">
					{menuDisabled ? (
						<Icon
							name={IconName.DotsVertical}
							className="h-4 w-4 text-disabled dark:text-zinc-600"
						/>
					) : (
						<PopoverMenu
							className="relative"
							items={menuItems}
							trigger={({ toggle }) => (
								<Button
									theme={ButtonTheme.IconNeutral}
									size={Size.SMALL}
									iconOnly
									type="button"
									onClick={toggle}
									aria-label={`Actions for ${connection.database_name}`}
								>
									<Icon name={IconName.DotsVertical} className="h-4 w-4" />
								</Button>
							)}
						/>
					)}
				</div>
			</header>
		</article>
	);
};
