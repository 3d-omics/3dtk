The catalogue
=============

``3dtk`` is a *consumer*. It never talks to Airtable, never rebuilds data, and
holds no secrets. It reads a published, checksummed SQLite artefact built by
`database-build <https://github.com/3d-omics/database-build>`_ and deposited on
Zenodo.

Identity
--------

=============================  ==========================================
Cite this (always latest)      ``10.5281/zenodo.22159111`` (concept DOI)
Version this release pins      ``10.5281/zenodo.22159112`` (version DOI)
``data_version``               ``2026.08.29``
``schema_version``             ``2``
Licence                        CC-BY-4.0
=============================  ==========================================

The **concept DOI is for citation**; the **version DOI is what the code pins**,
together with the artefact's SHA-256. A pinned build never silently follows
"latest", and a download whose checksum does not match is discarded rather than
used.

Every catalogue is self-identifying through its ``catalog_meta`` table, which
records ``data_version``, ``schema_version``, ``built_with_3domics_db_build``
and ``source_snapshot``. ``3dtk`` validates ``schema_version`` when opening a
catalogue and refuses one it cannot read.

Where the catalogue comes from
------------------------------

Resolution order — first hit wins:

1. an explicit ``--db`` / ``path=`` argument;
2. the ``PY3DTK_DB`` environment variable;
3. the user cache, populated by ``3dtk database sync`` or a lazy first-use
   download;
4. a bundled package resource, if one was shipped.

The published wheel bundles no catalogue, so step 3 is the normal path. Step 4
exists so that bundling is a packaging decision rather than an architectural
one.

.. code-block:: bash

   3dtk database info      # identity, size, checksum, and which source was used
   3dtk database where     # resolved path only; never downloads
   3dtk database sync      # download the pinned release into the cache

To use a catalogue you already have:

.. code-block:: bash

   3dtk --db /path/to/3domics-2026.08.29.sqlite genomes query
   export PY3DTK_DB=/path/to/3domics-2026.08.29.sqlite

Tables
------

Record tables, each carrying ``airtable_record_id`` and
``airtable_created_time``:

===========================  ===========================================
Table                        Holds
===========================  ===========================================
``experiments``              one row per 3D'omics experiment
``specimens``                sampled host animals
``macrosamples``             bulk samples taken from specimens
``cryosections``             sections cut from macrosamples
``microsamples``             laser-captured microsamples, with coordinates
``macrosample_sequencing``   macrosample sequencing libraries
``microsample_sequencing``   microsample sequencing libraries
===========================  ===========================================

Derived tables, parsed out of CSV attachments:

=========================  =============================================
Table                      Holds
=========================  =============================================
``genome_metadata``        per-experiment genome catalogues and taxonomy
``macro_genome_counts``    genome × macrosample-library counts (sparse)
``microsample_counts``     genome × microsample-library counts (sparse)
=========================  =============================================

Provenance tables:

===================  ================================================
Table                Holds
===================  ================================================
``catalog_meta``     version identity
``source_files``     one row per ingested attachment, with checksums
``matrix_axes``      the original row and column order of every matrix
===================  ================================================

Known data quirks
-----------------

**Specimen ``treatment_group`` holds Airtable record ids.** Values look like
``recMXDODTfnGcavHn``: an unresolved Airtable link field rather than a readable
label. ``3dtk`` displays ``treatment`` (``TC1``) and ``treatment_name``
(``ControlDiet+EarlyMannan``) instead, and keeps ``treatment_group`` filterable
because it is still a valid grouping key. Resolving the link is a
``database-build`` change.

**Some parent references are missing.** In the 2026.08.29 release, 185
``cryosection_id`` values referenced by ``microsamples`` have no row in
``cryosections``. ``3dtk`` uses outer joins throughout, so those microsamples
still appear, with empty parent columns, rather than silently disappearing from
counts.

**Not every cryosection has a count matrix.** 76 of 116 do.
