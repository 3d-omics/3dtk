Output formats
==============

Every command that returns rows supports the same three output modes.

Rich table (default)
--------------------

.. code-block:: bash

   3dtk genomes query --limit 5

CSV and TSV
-----------

.. code-block:: bash

   3dtk genomes query --csv
   3dtk genomes query --tsv
   3dtk genomes query --csv --output-file genomes.csv

``--csv`` and ``--tsv`` write to stdout unless ``--output-file`` is given, so
they pipe:

.. code-block:: bash

   3dtk genomes query --csv --limit 1000 | wc -l

``--csv`` and ``--tsv`` are mutually exclusive, and ``--output-file`` requires
one of them.

Choosing columns
----------------

``--columns`` takes a preset name, the word ``all``, or a comma-separated list:

.. code-block:: bash

   3dtk microsamples query --columns spatial
   3dtk microsamples query --columns all
   3dtk microsamples query --columns microsample_id,x_coord,y_coord

Presets differ per target. ``3dtk <target> query --help`` names them, and an
unrecognised preset tells you which are available for that target.

Common presets:

===================  =========================================================
Preset               Emphasis
===================  =========================================================
``default``          the identifying columns plus the most-used context
``all``              every available column
``spatial``          coordinates (microsamples, counts)
``context``          parent metadata carried down the hierarchy (microsamples)
``taxonomy``         full GTDB lineage (genomes, counts)
``accession``        external database accessions and links
``sequencing``       library identifiers and run accessions
===================  =========================================================

Limits
------

``query`` defaults to 50 rows. Pass ``--limit`` to change it.

Field discovery
---------------

.. code-block:: bash

   3dtk genomes fields              # what values --field accepts
   3dtk genomes fields --csv

Aliases are marked as such, with the canonical field they resolve to.
