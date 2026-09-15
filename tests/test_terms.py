"""The data-usage terms gate."""

from __future__ import annotations

import pytest
import typer
from rich.console import Console

from py3dtk.terms import TERMS_MESSAGE, ensure_terms_accepted


def test_accept_terms_skips_the_prompt(monkeypatch) -> None:
    def _fail(*args, **kwargs):
        raise AssertionError("must not prompt when --accept-terms was given")

    monkeypatch.setattr("py3dtk.terms.Confirm.ask", _fail)
    ensure_terms_accepted(Console(quiet=True), accept_terms=True)


def test_declining_exits_non_zero(monkeypatch) -> None:
    monkeypatch.setattr("py3dtk.terms.Confirm.ask", lambda *a, **k: False)
    with pytest.raises(typer.Exit) as excinfo:
        ensure_terms_accepted(Console(quiet=True), accept_terms=False)
    assert excinfo.value.exit_code == 1


def test_accepting_proceeds(monkeypatch) -> None:
    monkeypatch.setattr("py3dtk.terms.Confirm.ask", lambda *a, **k: True)
    ensure_terms_accepted(Console(quiet=True), accept_terms=False)


def test_non_interactive_input_gives_actionable_advice(monkeypatch, capsys) -> None:
    def _eof(*args, **kwargs):
        raise EOFError

    monkeypatch.setattr("py3dtk.terms.Confirm.ask", _eof)
    console = Console()
    with pytest.raises(typer.Exit):
        ensure_terms_accepted(console, accept_terms=False)
    assert "--accept-terms" in capsys.readouterr().out


def test_terms_state_the_licence_and_citation() -> None:
    """The gate states what the catalogue records, not invented policy."""
    assert "CC-BY-4.0" in TERMS_MESSAGE
    assert "10.5281/zenodo.22159111" in TERMS_MESSAGE
    assert "TODO" not in TERMS_MESSAGE
