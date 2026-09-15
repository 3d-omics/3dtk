Python API
==========

.. code-block:: python

   import py3dtk

   with py3dtk.Database() as db:
       genomes = db.genomes.query(quality="high", genus="Faeciplasma")

Remember the name split: install ``3dtk``, import ``py3dtk``.

Filters use the same names as the CLI options, with underscores instead of
hyphens. Sequences behave like comma-separated CLI values:

.. code-block:: python

   db.specimens.query(sex=["female", "male"])   # same as --sex female,male
   db.microsamples.query(x_min=13000, x_max=14000)

Database
--------

.. autoclass:: py3dtk.Database
   :members:
   :undoc-members:

Collections
-----------

.. autoclass:: py3dtk.api._Collection
   :members:

.. autoclass:: py3dtk.api._FetchableCollection
   :members:

.. autoclass:: py3dtk.api.CountsCollection
   :members:

Records
-------

.. autoclass:: py3dtk.Experiment
.. autoclass:: py3dtk.Specimen
.. autoclass:: py3dtk.Macrosample
.. autoclass:: py3dtk.Cryosection
.. autoclass:: py3dtk.Microsample
.. autoclass:: py3dtk.Genome
.. autoclass:: py3dtk.CountCell

Results
-------

.. autoclass:: py3dtk.ValuesResult
   :members:

.. autoclass:: py3dtk.ValueCount
   :members:

.. autoclass:: py3dtk.TargetStats
   :members:

.. autoclass:: py3dtk.StatBreakdown
   :members:

.. autoclass:: py3dtk.FetchSummary
   :members:

.. autoclass:: py3dtk.FetchPlan
   :members:

.. autoclass:: py3dtk.UnfetchableRecord
   :members:

Count matrices
--------------

.. autoclass:: py3dtk.DenseMatrix
   :members:

.. autoclass:: py3dtk.MatrixSource
   :members:

Catalogue
---------

.. autodata:: py3dtk.PINNED_CATALOG

.. autoclass:: py3dtk.catalog.CatalogRelease
   :members:

.. autofunction:: py3dtk.catalog.resolve_catalog_path

.. autofunction:: py3dtk.catalog.download_catalog

Exceptions
----------

.. autoclass:: py3dtk.UnsupportedSchemaVersionError
.. autoclass:: py3dtk.CatalogError
.. autoclass:: py3dtk.ChecksumMismatchError
.. autoclass:: py3dtk.CountsError
