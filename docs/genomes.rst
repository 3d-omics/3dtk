Genomes
=======

Per-experiment genome catalogues with GTDB taxonomy, completeness and
contamination.

Examples
--------

.. code-block:: bash

   3dtk genomes query --genus Faeciplasma --quality high
   3dtk genomes query --phylum Bacillota_A --columns taxonomy
   3dtk genomes query --completeness-min 90 --contamination-max 5
   3dtk genomes values --field genus --limit 10
   3dtk genomes stats --experiment-id G

Notes
-----

**Quality** is derived from completeness and contamination, MIMAG-style:

==========  ==========================================================
Tier        Definition
==========  ==========================================================
``high``    completeness >= 90 and contamination <= 5
``medium``  completeness >= 50 and contamination <= 10, and not high
``low``     everything else
==========  ==========================================================

The three tiers partition the catalogue exactly, so the counts sum to the total.

**Taxonomy** is stored with GTDB rank prefixes and displayed without them.
Filters accept either form. Rank options are ``--domain``, ``--phylum``,
``--class``, ``--order``, ``--family``, ``--genus`` and ``--species``.

**Genome IDs are scoped to an experiment**, not globally unique. See
:doc:`identifiers`.

All targets share the same actions; see :doc:`outputs` for output
formats and column presets.
