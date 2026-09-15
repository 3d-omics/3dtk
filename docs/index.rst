3dtk documentation
==================

The 3D'omics ToolKit (``3dtk``) is a Python package and command-line tool for
finding, summarising, exporting, and downloading records from the 3D'omics data
catalogue. It needs no credentials and no server: it reads a published,
checksummed SQLite artefact deposited on Zenodo under a citable DOI.

.. important::

   Python identifiers cannot begin with a digit, so ``import 3dtk`` is a
   ``SyntaxError``. Install the ``3dtk`` distribution and import the
   ``py3dtk`` package — the same split as ``scikit-learn`` → ``sklearn``.

   .. code-block:: bash

      pip install 3dtk

   .. code-block:: python

      import py3dtk

The data hierarchy
------------------

.. code-block:: text

   experiments → specimens → macrosamples → cryosections → microsamples
                                       ↘ genomes (per experiment)
                                       ↘ counts (genome × sample matrices)

Every level is a CLI group sharing the same action grammar, so learning one
teaches the rest: ``query`` lists matching records, ``values`` counts distinct
values of a field, ``stats`` summarises matches, and ``fields`` lists what
``values --field`` accepts. ``macrosamples`` and ``microsamples`` add ``fetch``;
``counts`` adds ``matrices`` and ``export``.

Quick example
-------------

.. code-block:: bash

   3dtk database sync
   3dtk microsamples query --experiment-id G --sex female --columns context
   3dtk genomes stats --quality high
   3dtk counts export --experiment-id G --level micro --csv --output-file G.csv

.. code-block:: python

   import py3dtk

   with py3dtk.Database() as db:
       genomes = db.genomes.query(quality="high", genus="Faeciplasma")
       matrix = db.counts.export(experiment_id="G", level="micro")

Contents
--------

.. toctree::
   :maxdepth: 2

   installation
   quickstart
   database
   identifiers
   outputs
   experiments
   specimens
   macrosamples
   cryosections
   microsamples
   genomes
   counts
   fetching
   api
   advanced
