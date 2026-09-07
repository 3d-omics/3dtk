Fetching data
=============

``fetch`` downloads the sequencing files behind matching records. It is
available on :doc:`macrosamples` and :doc:`microsamples` — the levels whose
records carry ENA accessions.

.. code-block:: bash

   3dtk microsamples fetch --cryosection-id G005bI205A --output-dir data
   3dtk macrosamples fetch --experiment-id G --data-type Metagenomics

How accessions become URLs
--------------------------

The catalogue stores ENA *browser links* and run accessions, not file URLs. So
``fetch`` is a two-stage operation: it queries the records, then resolves their
accessions through the `ENA Portal API
<https://www.ebi.ac.uk/ena/portal/api/>`_ before any bytes move.

Resolution is **batched**, so a 500-microsample fetch issues a handful of
requests rather than 500, and results are cached within a run.

Integrity
---------

ENA publishes an MD5 and a byte size for every FASTQ file. Every download is
checked against:

- the **MD5** ENA published for that file,
- the **byte size** ENA published,
- the ``Content-Length`` the server reported,
- a **streaming gzip integrity check** (header, per-member CRC32 and length),
  which also catches truncation when no MD5 is available.

A file that fails any check is recorded as ``corrupt`` and is never promoted to
its final name, so a failed download can never be mistaken for a good one.

Every file is logged to an append-only JSONL manifest
(``--manifest-path``, default ``manifest.jsonl``) with a timestamp, the record
id, URL, path, SHA-256, byte count and status.

Batch scripts
-------------

To download elsewhere — a cluster, a different network — write a script instead:

.. code-block:: bash

   3dtk microsamples fetch --experiment-id G --script download.sh

The generated script skips files that already exist, and re-verifies each MD5
itself, so a batch run gets the same integrity guarantee as a direct download.

Existing files
--------------

Files that already exist are skipped and reported as ``skipped_existing``. Pass
``--overwrite`` to re-download them.

Protocol
--------

Downloads default to HTTPS, which supports range requests and traverses
firewalls that block FTP. Pass ``--protocol ftp`` for the FTP endpoints.

Records that cannot be fetched
------------------------------

These are reported, not silently dropped:

========================  ================================================
Reason                    Meaning
========================  ================================================
``no_accession``          the record carries no ENA accession
``unresolved_accession``  ENA does not recognise the accession
``metabolights``          metabolomics data, published to MetaboLights
========================  ================================================

Metabolomics macrosamples point at MetaboLights (``MTBLS13210``) rather than
ENA. ``3dtk`` surfaces those accessions so you can retrieve them yourself; it
does not download from MetaboLights.

Terms of use
------------

A data-usage panel is shown before the first download of a session; pass
``--accept-terms`` to skip it.

.. note::

   The wording currently shipped is a placeholder marked ``TODO`` pending the
   consortium's agreed text. The catalogue itself is CC-BY-4.0.
