Advanced usage
==============

Raw SQL predicates
------------------

``--where`` appends a predicate to the generated query, for filters the options
do not cover:

.. code-block:: bash

   3dtk genomes query --where "completeness > 95 AND length > 3000000"
   3dtk microsamples query --where "x_coord IS NOT NULL" --columns spatial

The fragment is validated before use: semicolons, SQL comments, and mutating
keywords (``DROP``, ``DELETE``, ``INSERT``, ``UPDATE``, ``ALTER``, ``ATTACH``,
``CREATE``, ``PRAGMA``, …) are rejected, and the catalogue is opened read-only
regardless. It is an escape hatch, not an injection surface — but it is also not
a sandbox, so write predicates you understand.

``--where`` combines with the normal filters using ``AND``.

Column names available to ``--where`` are the *source* columns, which for
taxonomy means the raw GTDB values including prefixes:

.. code-block:: bash

   3dtk genomes query --where "genus = 'g__Faeciplasma'"

Using your own catalogue
------------------------

.. code-block:: bash

   3dtk --db ./3domics-2026.08.29.sqlite genomes query
   export THREEDTK_DB=./3domics-2026.08.29.sqlite

.. code-block:: python

   with threedtk.Database("./3domics-2026.08.29.sqlite") as db:
       ...

``3dtk`` validates ``schema_version`` on open and refuses a catalogue it cannot
read, so pointing at an older or newer artefact fails loudly rather than
returning wrong answers.

Scripting
---------

``--csv`` writes to stdout, so commands compose:

.. code-block:: bash

   3dtk microsamples query --experiment-id G --columns spatial --csv --limit 10000 \
     | python analyse.py

   for cryo in $(3dtk counts matrices --level micro --csv | tail -n +2 | cut -d, -f2); do
     3dtk counts export --cryosection-id "$cryo" --csv --output-file "$cryo.csv"
   done

Reproducibility
---------------

Record the exact catalogue you used:

.. code-block:: bash

   3dtk database info

That prints the ``data_version``, ``schema_version``, SHA-256 and pinned version
DOI. Cite the concept DOI (``10.5281/zenodo.22159111``) in a manuscript and give
the ``data_version`` for exactness; a reader can then retrieve the identical
artefact.

To pin a specific release for an analysis:

.. code-block:: bash

   python scripts/sync_catalog.py --data-version 2026.08.29 --download \
     --output ./3domics-2026.08.29.sqlite
   export THREEDTK_DB=$PWD/3domics-2026.08.29.sqlite

Performance
-----------

The catalogue is a local SQLite file, so most queries return in milliseconds.
The ``counts`` target unions ~350,000 rows through several joins; unfiltered
aggregate queries over it take a fraction of a second, and filtered ones are
faster. Dense exports are bounded by matrix size — the largest single matrix in
the 2026.08.29 release is about 67,000 cells.
