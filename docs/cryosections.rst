Cryosections
============

Sections cut from a macrosample. Each cryosection is the owner of a
microsample count matrix, and records its position, slide, and whether an image
exists.

Examples
--------

.. code-block:: bash

   3dtk cryosections query --has-image
   3dtk cryosections query --experiment-id G --columns slide
   3dtk cryosections values --field position
   3dtk cryosections stats

Notes
-----

``microsample_count`` is the declared number of microsamples cut from the
section, which is not always the number of ``microsamples`` rows present.

76 of the 116 cryosections in the 2026.08.29 release have a count matrix; use
``3dtk counts matrices --level micro`` to list those.

All targets share the same actions; see :doc:`outputs` for output
formats and column presets.
