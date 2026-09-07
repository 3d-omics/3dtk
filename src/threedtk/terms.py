"""Data-usage terms gate shown before downloads.

TODO(3d-omics): replace :data:`TERMS_MESSAGE` with the project's actual data
usage policy and contact address before the first public release. The text
below deliberately states only what the catalogue itself records (the CC-BY-4.0
licence) rather than inventing a coordination policy.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
import typer

# TODO(3d-omics): confirm wording and contact address with the consortium.
TERMS_MESSAGE = (
    "The 3D'omics data catalogue is published under CC-BY-4.0. If you use these "
    "data in a publication, cite the catalogue via its concept DOI "
    "(10.5281/zenodo.22159111) and the originating 3D'omics experiment.\n\n"
    "[yellow]TODO: this placeholder stands in for the 3D'omics data usage terms. "
    "Replace it with the consortium's agreed wording and contact address before "
    "the first public release.[/yellow]\n\n"
    "If you agree, you may use the --accept-terms flag in the future to suppress "
    "this prompt."
)


def ensure_terms_accepted(console: Console, *, accept_terms: bool) -> None:
    """Prompt for terms acceptance, or return immediately if already accepted.

    Raises:
        typer.Exit: If the user declines, or if no interactive input is
            available and ``--accept-terms`` was not passed.
    """
    if accept_terms:
        return

    console.print(Panel(TERMS_MESSAGE, title="Data Usage Terms", border_style="yellow"))
    try:
        accepted = Confirm.ask(
            "Do you confirm that you have read and accept these terms?",
            console=console,
            default=False,
        )
    except EOFError:
        console.print(
            "No interactive input is available. Re-run this command with "
            "--accept-terms if you have already read and accepted these terms."
        )
        raise typer.Exit(code=1) from None
    if not accepted:
        raise typer.Exit(code=1)
