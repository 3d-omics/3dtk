"""The ``3dtk experiments`` sub-app.

Commands are generated from the filter specifications in
:mod:`threedtk.filters`, so every target shares one action grammar.
"""

from __future__ import annotations

from threedtk.commands import build_target_app

app = build_target_app("experiments")
