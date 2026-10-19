# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The NEEM data folder: SQLite NEEMs dropped in a folder, merged into one database.

Every SQLite file (or SQLite ``.sql`` dump) in ``NEEM_DATA_DIR`` is loaded into
a single Postgres database, ``NEEM_DATABASE`` (``neem`` by default), on the
same server as the store. The ingestion service watches the folder
(:mod:`auto_ontology.neem_folder.watcher`) and keeps the database in step: a new
or changed file is (re)loaded, a removed file's rows are deleted, and the
catalog is re-ingested afterwards.

* :mod:`~auto_ontology.neem_folder.config` -- settings and the connection string.
* :mod:`~auto_ontology.neem_folder.files` -- which files in the folder count.
* :mod:`~auto_ontology.neem_folder.merge` -- loading one file into the database.
* :mod:`~auto_ontology.neem_folder.watcher` -- the polling loop.
"""
