// SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Connector kinds supported in the new-connection wizard. */
export enum ConnectionType {
	DATABRICKS = 'databricks',
	POSTGRESQL = 'postgresql',
	MYSQL = 'mysql',
	SNOWFLAKE = 'snowflake',
}

export const connectionDisplayName: Record<ConnectionType, string> = {
	[ConnectionType.DATABRICKS]: 'Databricks',
	[ConnectionType.POSTGRESQL]: 'PostgreSQL',
	[ConnectionType.MYSQL]: 'MySQL',
	[ConnectionType.SNOWFLAKE]: 'Snowflake',
};

export const isConnectionType = (value: string | null | undefined): value is ConnectionType =>
	typeof value === 'string' && (Object.values(ConnectionType) as string[]).includes(value);

export type ConnectionFieldKey =
	| 'host'
	| 'http_path'
	| 'port'
	| 'account'
	| 'warehouse'
	| 'user'
	| 'password'
	| 'private_key'
	| 'private_key_passphrase'
	| 'database'
	| 'schema'
	| 'table_allow_regex'
	| 'table_deny_regex';

export type ConnectionField = {
	key: ConnectionFieldKey;
	label: string;
	placeholder?: string;
	secret?: boolean;
	/** Optional fields are not required to enable Test/Create. */
	optional?: boolean;
	/** Sent with the connection test only; stripped before the connection is created. */
	testOnly?: boolean;
	/** Rendered as a checkbox and sent as a boolean rather than a string. */
	boolean?: boolean;
	/** Rendered as a textarea. Needed for pasted PEM keys, which span many lines. */
	multiline?: boolean;
	/** Rendered as a file picker; the value is the file's base64-encoded bytes. */
	file?: boolean;
	/** `accept` attribute for a file field. */
	fileAccept?: string;
	/** Helper text shown under the field. */
	hint?: string;
};

/**
 * Fields where supplying any one satisfies the requirement, so none of them can
 * be marked required on its own.
 *
 * Snowflake accounts that enforce MFA reject password sign-in for person users
 * and forbid passwords on service users, leaving a key pair as the only usable
 * credential. Accounts without that enforcement still take a password, so the
 * form has to accept either.
 */
export const CONNECTION_EITHER_FIELDS: Partial<Record<ConnectionType, ConnectionFieldKey[]>> = {
	[ConnectionType.SNOWFLAKE]: ['password', 'private_key'],
};

/** Form fields rendered per connector type. `database` is the connection identity. */
export const CONNECTION_FIELDS: Record<ConnectionType, ConnectionField[]> = {
	[ConnectionType.DATABRICKS]: [
		{
			key: 'host',
			label: 'Server Hostname',
			placeholder: 'dbc-a1b2345c-d6e7.cloud.databricks.com',
		},
		{
			key: 'http_path',
			label: 'HTTP Path',
			placeholder: '/sql/1.0/warehouses/a1b234c567d8e9fa',
		},
		{ key: 'password', label: 'Access Token', secret: true },
		{ key: 'database', label: 'Catalog', placeholder: 'main' },
		{
			key: 'schema',
			label: 'Schema',
			placeholder: 'Leave Empty to Choose from a List',
			hint: 'Ingest only this schema. The connection test verifies it exists, and the schema selection step is skipped. Leave empty to pick schemas from a list instead.',
			optional: true,
			testOnly: true,
		},
	],
	[ConnectionType.POSTGRESQL]: [
		{ key: 'host', label: 'Host', placeholder: 'localhost' },
		{ key: 'port', label: 'Port', placeholder: '5432' },
		{ key: 'user', label: 'User', placeholder: 'postgres' },
		{ key: 'password', label: 'Password', secret: true },
		{ key: 'database', label: 'Database', placeholder: 'my_database' },
	],
	[ConnectionType.MYSQL]: [
		{ key: 'host', label: 'Host', placeholder: 'localhost' },
		{ key: 'port', label: 'Port', placeholder: '3306', optional: true },
		{ key: 'user', label: 'User', placeholder: 'root' },
		{ key: 'password', label: 'Password', secret: true },
		{ key: 'database', label: 'Database', placeholder: 'my_database' },
	],
	[ConnectionType.SNOWFLAKE]: [
		{ key: 'account', label: 'Account', placeholder: 'xy12345.us-east-1' },
		{ key: 'warehouse', label: 'Warehouse', placeholder: 'COMPUTE_WH' },
		{ key: 'user', label: 'User' },
		{
			key: 'password',
			label: 'Password',
			secret: true,
			optional: true,
			hint: 'Leave empty and paste a private key below if the account enforces MFA, which blocks password sign-in for unattended services.',
		},
		{
			key: 'private_key',
			label: 'Private Key (PEM)',
			placeholder: '-----BEGIN PRIVATE KEY-----',
			secret: true,
			optional: true,
			multiline: true,
			hint: 'Key-pair authentication. Paste the full PEM for a key registered on the Snowflake user. Used instead of a password.',
		},
		{
			key: 'private_key_passphrase',
			label: 'Private Key Passphrase',
			secret: true,
			optional: true,
			hint: 'Only needed if the private key above is encrypted.',
		},
		{ key: 'database', label: 'Database', placeholder: 'MY_DATABASE' },
	],
};

/**
 * Fields offered for every connector, appended after the type-specific ones.
 *
 * Kept separate rather than copied into every list: they are enforced
 * centrally at catalog extraction (`auto_ontology/catalog/table_filter.py`), so
 * every connector honours them identically and none may drift.
 */
export const COMMON_CONNECTION_FIELDS: ConnectionField[] = [
	{
		key: 'table_allow_regex',
		label: 'Table Allowlist (Regex)',
		placeholder: 'Leave Empty to Ingest Every Table',
		optional: true,
		hint: 'Ingest only tables whose name matches. Unanchored and case-sensitive, so "fact_" matches "fact_sales"; anchor with ^ and $ for an exact name.',
	},
	{
		key: 'table_deny_regex',
		label: 'Table Denylist (Regex)',
		placeholder: 'Leave Empty to Exclude Nothing',
		optional: true,
		hint: 'Skip tables whose name matches, even if the allowlist also matches them. Use this for relations the warehouse lists but cannot actually read, such as a broken Distributed table or a Kafka queue.',
	},
];

/** Form fields for a connector: its own, plus the ones shared by all of them. */
export const connectionFieldsFor = (type: ConnectionType): ConnectionField[] => [
	...CONNECTION_FIELDS[type],
	...COMMON_CONNECTION_FIELDS,
];
