Installation
============

.. code-block:: bash

   pip install 3dtk

Requires Python 3.10 or newer.

The name split
--------------

The distribution and the console script are ``3dtk``; the import package is
``threedtk``:

=======================  ============
Surface                  Name
=======================  ============
PyPI distribution        ``3dtk``
Console script           ``3dtk``
Import package           ``threedtk``
=======================  ============

This is not a typo. Python identifiers cannot begin with a digit, so
``import 3dtk`` raises ``SyntaxError``. ``scikit-learn`` → ``sklearn`` solves the
same problem the same way.

Getting the catalogue
---------------------

The wheel ships **no** catalogue. Fetch it once:

.. code-block:: bash

   3dtk database sync

That downloads the pinned release (59 MB) into a per-user cache and verifies it
against a SHA-256 recorded in the package. Any command that needs data will also
download it lazily on first use, so ``database sync`` is only a way to do it
deliberately.

To check what you have, without downloading anything:

.. code-block:: bash

   3dtk database where     # prints the resolved path, or explains what to do
   3dtk database info      # full identity: version, schema, checksum, source

Development install
-------------------

.. code-block:: bash

   git clone https://github.com/3d-omics/3dtk
   cd 3dtk
   python -m pip install -e ".[dev]"
   python -m pytest

The test suite builds a miniature catalogue in a temporary directory and makes
no network calls.
