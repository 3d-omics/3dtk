Experiments
===========

The top of the hierarchy: one row per 3D'omics experiment, with its
BioProject accession, MAG summary statistics, and whether it has a genome
catalogue.

Examples
--------

.. code-block:: bash

   3dtk experiments query
   3dtk experiments query --has-genome-catalogue --columns mag
   3dtk experiments values --field experiment_type
   3dtk experiments stats

Notes
-----

Six of the eight experiments in the 2026.08.29 release have a genome
catalogue; ``--has-genome-catalogue`` selects them, and only those experiments
have rows in :doc:`genomes` and :doc:`counts`.

All targets share the same actions; see :doc:`outputs` for output
formats and column presets.
