"""The ``3dtk counts`` sub-app.

Adds ``matrices`` and ``export`` on top of the shared action grammar. The module
is named ``counts_cli`` so it does not shadow :mod:`threedtk.counts`, which holds
the dense-matrix logic.
"""

from __future__ import annotations

from threedtk.commands import add_counts_commands, build_target_app

app = add_counts_commands(build_target_app("counts"))
