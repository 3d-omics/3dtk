Python API
==========

.. code-block:: python

   import threedtk

   with threedtk.Database() as db:
       genomes = db.genomes.query(quality="high", genus="Faeciplasma")

Remember the name split: install ``3dtk``, import ``threedtk``.

Filters use the same names as the CLI options, with underscores instead of
hyphens. Sequences behave like comma-separated CLI values:

.. code-block:: python

   db.specimens.query(sex=["female", "male"])   # same as --sex female,male
   db.microsamples.query(x_min=13000, x_max=14000)

Database
--------

.. autoclass:: threedtk.Database
   :members:
   :undoc-members:

Collections
-----------

.. autoclass:: threedtk.api._Collection
   :members:

.. autoclass:: threedtk.api._FetchableCollection
   :members:

.. autoclass:: threedtk.api.CountsCollection
   :members:

Records
-------

.. autoclass:: threedtk.Experiment
.. autoclass:: threedtk.Specimen
.. autoclass:: threedtk.Macrosample
.. autoclass:: threedtk.Cryosection
.. autoclass:: threedtk.Microsample
.. autoclass:: threedtk.Genome
.. autoclass:: threedtk.CountCell

Results
-------

.. autoclass:: threedtk.ValuesResult
   :members:

.. autoclass:: threedtk.ValueCount
   :members:

.. autoclass:: threedtk.TargetStats
   :members:

.. autoclass:: threedtk.StatBreakdown
   :members:

.. autoclass:: threedtk.FetchSummary
   :members:

.. autoclass:: threedtk.FetchPlan
   :members:

.. autoclass:: threedtk.UnfetchableRecord
   :members:

Count matrices
--------------

.. autoclass:: threedtk.DenseMatrix
   :members:

.. autoclass:: threedtk.MatrixSource
   :members:

Catalogue
---------

.. autodata:: threedtk.PINNED_CATALOG

.. autoclass:: threedtk.catalog.CatalogRelease
   :members:

.. autofunction:: threedtk.catalog.resolve_catalog_path

.. autofunction:: threedtk.catalog.download_catalog

Exceptions
----------

.. autoclass:: threedtk.UnsupportedSchemaVersionError
.. autoclass:: threedtk.CatalogError
.. autoclass:: threedtk.ChecksumMismatchError
.. autoclass:: threedtk.CountsError
