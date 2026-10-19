// SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
// All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Suspense } from 'react';
import { OntologiesView } from '@/components/ontologiesPage';

/**
 * The selected ontology, tab and element live in the URL (`?o=`, `?tab=`,
 * `?iri=`) so a view can be bookmarked or shared. The view reads them with
 * `useSearchParams`, which needs this Suspense boundary.
 */
export default function OntologiesPage() {
	return (
		<Suspense fallback={null}>
			<OntologiesView />
		</Suspense>
	);
}
