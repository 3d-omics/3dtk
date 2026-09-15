"""The ``3dtk microsamples`` sub-app.

Adds ``fetch``: these records carry ENA accessions, which are resolved to FASTQ
URLs through the ENA Portal API at fetch time.
"""

from __future__ import annotations

from py3dtk.commands import add_fetch_command, build_target_app

app = add_fetch_command(build_target_app("microsamples"), "microsamples")
