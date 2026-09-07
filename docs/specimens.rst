Specimens
=========

Sampled host animals, joined to their experiment. Carries host species,
sex, life stage, treatment, pen, weight and days post infection.

Examples
--------

.. code-block:: bash

   3dtk specimens query --experiment-id G --sex female
   3dtk specimens query --species 'Gallus gallus' --columns treatment
   3dtk specimens query --weight-min 2.0 --weight-max 3.0
   3dtk specimens values --field treatment_name
   3dtk specimens stats --experiment-id G

Notes
-----

``--species`` matches either the scientific or the common name, so
``--species chicken`` and ``--species 'Gallus gallus'`` both work.

``treatment_group`` holds unresolved Airtable record ids, so displays use
``treatment`` and ``treatment_name``; see :doc:`database`.

All targets share the same actions; see :doc:`outputs` for output
formats and column presets.
