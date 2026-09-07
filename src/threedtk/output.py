from __future__ import annotations

import csv
from pathlib import Path
import sys
from typing import Iterable, TextIO

from rich.console import Console
from rich.table import Table
import typer


def validate_export_options(
    csv_output: bool,
    tsv_output: bool,
    output_file: Path | None,
) -> None:
    if csv_output and tsv_output:
        typer.echo("Use only one of --csv or --tsv.", err=True)
        raise typer.Exit(code=2)
    if output_file is not None and not (csv_output or tsv_output):
        typer.echo("Use --output-file only with --csv or --tsv.", err=True)
        raise typer.Exit(code=2)


def render_or_export_rows(
    console: Console,
    headers: tuple[str, ...],
    rows: list[dict],
    *,
    title: str,
    csv_output: bool = False,
    tsv_output: bool = False,
    output_file: Path | None = None,
) -> None:
    validate_export_options(csv_output, tsv_output, output_file)

    if csv_output or tsv_output:
        delimiter = "," if csv_output else "\t"
        if output_file is None:
            _write_delimited_rows_to_handle(sys.stdout, headers, rows, delimiter=delimiter)
        else:
            _write_delimited_rows(output_file, headers, rows, delimiter=delimiter)
            typer.echo(f"Wrote {len(rows)} rows to {output_file}.", err=True)
        return

    if not rows:
        console.print(f"No matching {title.lower()} found.")
        return

    table = Table(title=title)
    for header in headers:
        table.add_column(header)

    for row in rows:
        table.add_row(*(str(row[header]) if row[header] is not None else "" for header in headers))

    console.print(table)


def _write_delimited_rows(
    path: Path,
    headers: tuple[str, ...],
    rows: Iterable[dict],
    *,
    delimiter: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as handle:
        _write_delimited_rows_to_handle(handle, headers, rows, delimiter=delimiter)


def _write_delimited_rows_to_handle(
    handle: TextIO,
    headers: tuple[str, ...],
    rows: Iterable[dict],
    *,
    delimiter: str,
) -> None:
    writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow("" if row[header] is None else str(row[header]) for header in headers)
