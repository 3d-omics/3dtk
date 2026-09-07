Microsamples
============

The spatial unit of 3D'omics: laser-captured microsamples with coordinates,
joined all the way up to their experiment, and across to their sequencing
library.

Examples
--------

.. code-block:: bash

   3dtk microsamples query --experiment-id G --sex female --columns context
   3dtk microsamples query --x-min 13000 --x-max 14000 --y-min 18000 --y-max 19000 --columns spatial
   3dtk microsamples query --cryosection-id G005bI205A --columns sequencing
   3dtk microsamples query --has-sequencing --sample-type Positive
   3dtk microsamples stats --experiment-id G
   3dtk microsamples fetch --cryosection-id G005bI205A --output-dir data

Notes
-----

**Two coordinate systems.** ``x_coord``/``y_coord`` are
laser-microdissection stage coordinates recorded against the microsample;
``pixel_x``/``pixel_y`` are image coordinates recorded against the sequencing
library. Both are available on one row, and both are filterable as bounding
boxes (``--x-min``/``--x-max``/``--y-min``/``--y-max`` and
``--pixel-x-min`` and friends).

**Two identifiers.** ``microsample_id`` (``G121eI102A003``) identifies the
captured microsample; ``library_id`` (``M300653``) identifies its sequencing
library. They are different namespaces joined on the ENA accession — see
:doc:`identifiers`.

The ``context`` preset is the cross-level view: microsample, cryosection
position, macrosample, specimen, host species, sex, treatment, and
coordinates.

All targets share the same actions; see :doc:`outputs` for output
formats and column presets.
