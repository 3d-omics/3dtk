Identifiers
===========

Getting identifiers right matters more in this catalogue than in most, because
two of them are not what they look like.

Microsamples have two identifier namespaces
-------------------------------------------

This is the single most important thing to know.

============================================  ==========================  =====================
Column                                        Example                     Coordinates
============================================  ==========================  =====================
``microsamples.microsample_id``               ``G121eI102A003``           ``x_coord``/``y_coord``
``microsample_sequencing.microsample_id``     ``M300653``                 ``pixel_x``/``pixel_y``
============================================  ==========================  =====================

They share **no values whatsoever**. Joining the two tables on
``microsample_id`` yields zero rows. The tables are related through the **ENA
run accession** instead:

.. code-block:: sql

   microsamples.ena_accession = microsample_sequencing.run_accession

That match is one-to-one and covers all 4,463 sequencing rows. ``3dtk`` does
this join for you, so ``3dtk microsamples query --columns all`` returns both
identifiers and both coordinate systems on one row: ``microsample_id`` for the
captured microsample and ``library_id`` for its sequencing library.

The same bridge links ``macrosamples.ena_accession`` to
``macrosample_sequencing.run_accession``.

Count matrix columns are library IDs
------------------------------------

The sample axis of both count tables holds *sequencing library* identifiers, not
sample identifiers:

- ``macro_genome_counts.macrosample`` holds ``macrosample_sequencing.library_id``
  values (``D300418``);
- ``microsample_counts.microsample`` holds
  ``microsample_sequencing.microsample_id`` values (``M300653``).

So a count column reaches its sample metadata through the sequencing table and
then across the accession bridge. ``3dtk counts export --coordinates`` does that
walk and writes the result as a companion table aligned to the matrix columns.

Genome IDs are not globally unique
----------------------------------

Genome identifiers are ``<library>:<bin>``, for example
``D300418:bin_000001``. They are scoped to **an experiment's catalogue**, not to
the catalogue as a whole: the 2026.08.29 release has 3,313 genome rows but only
2,762 distinct genome strings, because some genomes appear in two experiments.

The key is therefore ``(experiment_id, genome)``. When you filter by ``--genome``
without an ``--experiment-id`` you may get rows from more than one experiment.

Taxonomy carries GTDB prefixes
------------------------------

The catalogue stores ``d__Bacteria``, ``p__Bacillota_A``,
``s__Faeciplasma gallinarum``. ``3dtk`` strips the rank prefix for display while
keeping the raw value filterable, so both of these work and mean the same thing:

.. code-block:: bash

   3dtk genomes query --genus Faeciplasma
   3dtk genomes query --genus g__Faeciplasma

Accession columns are browser links
-----------------------------------

``ena_link`` is a human-facing URL
(``https://www.ebi.ac.uk/ena/browser/view/ERR15114245``), not a file URL. To get
FASTQ files, use ``fetch``, which resolves accessions through the ENA Portal
API. See :doc:`fetching`.

Metabolomics macrosamples carry a ``metabolights_accession`` (``MTBLS13210``)
instead of an ENA accession.
