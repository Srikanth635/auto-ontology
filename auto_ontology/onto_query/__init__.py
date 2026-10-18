# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OntoQuerying: natural-language access to an existing OWL/RDF ontology.

The SQL side of the app builds a semantic layer from a database and answers
questions with SQL. This package does the second half of that -- retrieval and
LLM reasoning -- over an ontology someone has already written:

* :mod:`.loader` reads OWL/RDF into :class:`~.model.Element` records, one per
  class, property and individual, each with a searchable text description.
* :mod:`.index` indexes those descriptions twice, by embedding (pgvector or an
  in-memory matrix) and by keyword (BM25), and fuses the two rankings.
* :mod:`.retrieval` finds the elements a question is about and expands a small
  neighbourhood of the graph around them.
* On top of that sit the features: :mod:`.candidates` (find suitable
  concepts), :mod:`.qa` (answer questions with SPARQL), :mod:`.grow`
  (placement, duplicates, gaps, definitions), :mod:`.align` (match two
  ontologies) and :mod:`.shapes` (SHACL shapes and data validation).

The LLM never sees the whole ontology, only the retrieved neighbourhood, so the
same code serves a 50-class ontology and a 50,000-class one.
"""
