Counts
======

Genome × sample abundance matrices, at both the macrosample and microsample
levels, with taxonomy and spatial coordinates attached.

Examples
--------

.. code-block:: bash

   3dtk counts query --level micro --genus Faeciplasma --columns spatial
   3dtk counts stats --experiment-id G
   3dtk counts matrices --level micro --experiment-id G
   3dtk counts export --cryosection-id G005bI205A --csv --output-file counts.csv
   3dtk counts export --experiment-id G --level micro --csv --output-file G.csv --coordinates G_coords.csv
   3dtk counts export --cryosection-id G005bI205A --genus Faeciplasma --long --csv

Notes
-----

``query`` treats the counts as rows — one per non-zero cell, carrying
genome taxonomy and sample coordinates. ``export`` treats them as a matrix.

Rebuilding the dense matrix
---------------------------

The count tables are **sparse**: zeros are dropped, which is about five-sixths
of the microsample cells. ``export`` restores them.

The axes come from ``matrix_axes``, which preserves the original row and column
order of every ingested matrix — *not* from ``SELECT DISTINCT`` over the sparse
rows. That distinction matters: a genome whose row is entirely zero has no
sparse rows at all, and would silently vanish from a ``DISTINCT``-derived axis,
changing the matrix shape. Reconstruction is checked against
``source_files.row_count``, the catalogue's own record of how many non-zero
cells each matrix had.

Merging matrices
----------------

Every microsample matrix within an experiment shares an identical genome axis,
so selecting several merges them — the genome axis is unioned and the sample
columns concatenated:

.. code-block:: bash

   3dtk counts export --experiment-id G --level micro --csv --output-file G.csv

For the 2026.08.29 release that turns experiment G's 35 cryosection matrices
into a single 223 × 1512 matrix.

Output shapes
-------------

==========================  =================================================
Option                      Shape
==========================  =================================================
(default)                   wide: one row per genome, one column per sample
``--long``                  tidy ``genome,sample,count`` rows, non-zero only
``--long --include-zeros``  tidy rows including the restored zeros
``--coordinates PATH``      companion table aligned to the matrix columns
==========================  =================================================

The coordinate companion is what makes an export usable for spatial analysis:
one row per matrix column, in matrix order, carrying ``x_coord``/``y_coord``,
``pixel_x``/``pixel_y``, sample type and size. A column whose library has no
microsample behind it still gets a row, with empty coordinates, so the two files
always line up.

Filtering an export
-------------------

Rows can be restricted by genome ID or by any GTDB rank; columns by sample ID:

.. code-block:: bash

   3dtk counts export --experiment-id G --level micro --phylum Bacillota_A
   3dtk counts export --cryosection-id G005bI205A --sample M302869,M302866

Filtered exports skip the round-trip check, since the non-zero total is no
longer expected to match the catalogue's recorded figure.

All targets share the same actions; see :doc:`outputs` for output
formats and column presets.
