Macrosamples
============

Bulk samples taken from specimens, joined to their specimen, experiment and
sequencing library. Splits into metagenomics and metabolomics via
``data_type``.

Examples
--------

.. code-block:: bash

   3dtk macrosamples query --data-type Metagenomics --has-ena
   3dtk macrosamples query --data-type Metabolomics --columns accession
   3dtk macrosamples query --sample-type Caecum --columns sequencing
   3dtk macrosamples values --field sample_type
   3dtk macrosamples fetch --experiment-id G --script download.sh

Notes
-----

Metagenomics macrosamples carry an ENA accession; metabolomics macrosamples
carry a MetaboLights accession (``MTBLS13210``) instead. ``fetch`` downloads the
former and surfaces the latter rather than pretending it can retrieve them — see
:doc:`fetching`.

``library_id``, ``run_accession`` and ``experimental_unit`` come from
``macrosample_sequencing``, reached across the ENA-accession bridge described in
:doc:`identifiers`.

All targets share the same actions; see :doc:`outputs` for output
formats and column presets.
