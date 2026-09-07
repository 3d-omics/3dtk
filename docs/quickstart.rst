Quickstart
==========

.. code-block:: bash

   pip install 3dtk
   3dtk database sync

Running ``3dtk`` with no arguments prints what the catalogue contains:

.. code-block:: bash

   3dtk

Find records
------------

.. code-block:: bash

   3dtk experiments query
   3dtk specimens query --experiment-id G --sex female
   3dtk genomes query --genus Faeciplasma --quality high

Filters accept comma-separated values and are case-insensitive:

.. code-block:: bash

   3dtk specimens query --sex female,male
   3dtk genomes query --phylum Bacillota_A,Bacteroidota

Ask what values exist
---------------------

Before filtering on a field, see what is in it:

.. code-block:: bash

   3dtk genomes fields                       # which fields can I ask about?
   3dtk genomes values --field phylum        # what values does phylum take?
   3dtk microsamples values --field sample_type --experiment-id G

``values`` applies your filters first, so it answers "what is in *this* subset".

Summarise
---------

.. code-block:: bash

   3dtk genomes stats --quality high
   3dtk microsamples stats --experiment-id G

Cross-level questions
---------------------

Each level carries its parents' metadata, so one query spans the hierarchy:

.. code-block:: bash

   3dtk microsamples query --experiment-id G --sex female --columns context

That returns every microsample from female specimens in experiment G with its
host species, treatment, cryosection position and spatial coordinates — without
you writing a five-table join.

Export a count matrix
---------------------

.. code-block:: bash

   3dtk counts matrices --level micro
   3dtk counts export --cryosection-id G005bI205A --csv --output-file counts.csv \
                      --coordinates coords.csv

Download sequencing data
------------------------

.. code-block:: bash

   3dtk microsamples fetch --cryosection-id G005bI205A --output-dir data

Use ``--script download.sh`` to write a batch script instead of downloading now.

Python
------

.. code-block:: python

   import threedtk

   with threedtk.Database() as db:
       print(db.specimens.count(sex="female"))
       for row in db.genomes.values("phylum", limit=5).rows:
           print(row.value, row.count)
