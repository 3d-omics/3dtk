"""The ``3dtk`` command-line entry point."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import typer
from typer.core import TyperGroup

from py3dtk import __version__
from py3dtk.catalog import (
    PINNED_CATALOG,
    CatalogError,
    cache_dir,
    cached_catalog_path,
    catalog_source_label,
    download_catalog,
    file_sha256,
)
from py3dtk.counts_cli.commands import app as counts_app
from py3dtk.cryosections.commands import app as cryosections_app
from py3dtk.experiments.commands import app as experiments_app
from py3dtk.genomes.commands import app as genomes_app
from py3dtk.macrosamples.commands import app as macrosamples_app
from py3dtk.microsamples.commands import app as microsamples_app
from py3dtk.query import connect, read_catalog_meta, resolve_catalog_path
from py3dtk.specimens.commands import app as specimens_app

ROOT_TITLE = "3D'omics ToolKit"
ROOT_DESCRIPTION = (
    "Query, summarise, export, and download the 3D'omics data catalogue."
)


class RootHeaderGroup(TyperGroup):
    """Print the project header above the root help."""

    def format_help(self, ctx, formatter) -> None:
        if self.rich_markup_mode is not None:
            from typer import rich_utils

            console = rich_utils._get_rich_console()
            _print_root_header(console)
            console.print()
            return rich_utils.rich_format_help(
                obj=self, ctx=ctx, markup_mode=self.rich_markup_mode
            )

        formatter.write(_render_root_header_text())
        formatter.write("\n\n")
        return super().format_help(ctx, formatter)


app = typer.Typer(
    cls=RootHeaderGroup,
    help=ROOT_DESCRIPTION,
    no_args_is_help=False,
    add_completion=False,
)

app.add_typer(experiments_app, name="experiments")
app.add_typer(specimens_app, name="specimens")
app.add_typer(macrosamples_app, name="macrosamples")
app.add_typer(cryosections_app, name="cryosections")
app.add_typer(microsamples_app, name="microsamples")
app.add_typer(genomes_app, name="genomes")
app.add_typer(counts_app, name="counts")

database_app = typer.Typer(
    help="Inspect, locate, and synchronise the SQLite catalogue.",
    no_args_is_help=False,
)
app.add_typer(database_app, name="database")

from typer import rich_utils  # noqa: E402

_ORIGINAL_RICH_FORMAT_ERROR = rich_utils.rich_format_error


def _rich_format_error_with_root_header(self) -> None:
    ctx = getattr(self, "ctx", None)
    if ctx is not None and isinstance(ctx.find_root().command, RootHeaderGroup):
        console = Console(stderr=True)
        _print_root_header(console)
        console.print()
    _ORIGINAL_RICH_FORMAT_ERROR(self)


rich_utils.rich_format_error = _rich_format_error_with_root_header


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the 3dtk version and exit.",
    ),
    db: Path | None = typer.Option(
        None,
        "--db",
        help="Path to an alternate SQLite catalogue.",
    ),
) -> None:
    # `database sync` and `database where` must work before a catalogue exists,
    # so they resolve it themselves rather than through this callback.
    invoked = ctx.invoked_subcommand
    if invoked == "database":
        ctx.obj = {"catalog_option": db}
        return

    try:
        catalog_path = resolve_catalog_path(db)
    except CatalogError as exc:
        raise typer.BadParameter(str(exc), param_hint="--db") from exc
    if not catalog_path.exists():
        raise typer.BadParameter(
            f"Catalogue does not exist: {catalog_path}", param_hint="--db"
        )

    ctx.obj = {"catalog_path": catalog_path}

    if invoked is None:
        _print_root_overview(catalog_path)
        raise typer.Exit()


@database_app.callback(invoke_without_command=True)
def database_main(ctx: typer.Context) -> None:
    """Show the catalogue 3dtk is using."""
    if ctx.invoked_subcommand is not None:
        return
    _show_database(_catalog_option(ctx))


@database_app.command("sync")
def database_sync(
    ctx: typer.Context,
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Re-download even if the catalogue is already cached."
    ),
) -> None:
    """Download the pinned catalogue release into the local cache."""
    console = Console()
    destination = cached_catalog_path()
    console.print(
        f"Pinned release: [bold]{PINNED_CATALOG.data_version}[/bold] "
        f"(schema {PINNED_CATALOG.schema_version}, DOI {PINNED_CATALOG.version_doi})"
    )
    try:
        path = download_catalog(
            destination, overwrite=overwrite, progress=console.print
        )
    except CatalogError as exc:
        console.print(f"[red]Catalogue sync failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"Catalogue ready at {path}.")


@database_app.command("where")
def database_where(ctx: typer.Context) -> None:
    """Print the resolved catalogue path, without downloading anything."""
    try:
        path = resolve_catalog_path(_catalog_option(ctx), auto_download=False)
    except CatalogError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(path))


@database_app.command("info")
def database_info(ctx: typer.Context) -> None:
    """Report the catalogue's path, size, version identity, and checksum."""
    _show_database(_catalog_option(ctx))


def _catalog_option(ctx: typer.Context) -> Path | None:
    root = ctx.find_root()
    if root.obj and "catalog_option" in root.obj:
        return root.obj["catalog_option"]
    return None


def _show_database(db: Path | None) -> None:
    console = Console()
    try:
        catalog_path = resolve_catalog_path(db)
    except CatalogError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if not catalog_path.exists():
        raise typer.BadParameter(
            f"Catalogue does not exist: {catalog_path}", param_hint="--db"
        )

    meta = read_catalog_meta(catalog_path)
    details = {
        "Package version": __version__,
        "Catalogue source": catalog_source_label(catalog_path),
        "Catalogue path": str(catalog_path),
        "Catalogue size": _format_bytes(catalog_path.stat().st_size),
        "Data version": meta.get("data_version", "unknown"),
        "Schema version": meta.get("schema_version", "unknown"),
        "Built with": meta.get("built_with_3domics_db_build", "unknown"),
        "Source snapshot": meta.get("source_snapshot", "unknown"),
        "SHA256": file_sha256(catalog_path),
        "Pinned release": (
            f"{PINNED_CATALOG.data_version} ({PINNED_CATALOG.version_doi})"
        ),
        "Cite": f"{PINNED_CATALOG.concept_doi} ({PINNED_CATALOG.license})",
        "Cache directory": str(cache_dir()),
    }

    console.print("Catalogue", style="bold")
    for field, value in details.items():
        console.print(f"{field}: {value}")

    if meta.get("data_version") not in (None, PINNED_CATALOG.data_version):
        console.print(
            f"[yellow]Note:[/yellow] this catalogue is data_version "
            f"{meta.get('data_version')}, not the pinned {PINNED_CATALOG.data_version}."
        )


def _print_root_overview(catalog_path: Path) -> None:
    console = Console()
    _print_root_header(console)
    console.print()

    meta = read_catalog_meta(catalog_path)
    console.print(
        f"Catalogue {meta.get('data_version', 'unknown')} "
        f"(schema {meta.get('schema_version', 'unknown')}) at {catalog_path}"
    )

    table = Table(title="Catalogue contents")
    table.add_column("Level")
    table.add_column("Records", justify="right")
    table.add_column("Summary")
    for level, records, summary in _catalog_summary(catalog_path):
        table.add_row(level, records, summary)
    console.print(table)
    console.print("Use `3dtk --help` to see all commands.")


_SUMMARY_QUERIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "Experiments",
        "SELECT COUNT(*) FROM experiments",
        "SELECT COUNT(*) FROM experiments WHERE has_genome_catalogue = 1",
        "with a genome catalogue",
    ),
    (
        "Specimens",
        "SELECT COUNT(*) FROM specimens",
        "SELECT COUNT(DISTINCT species_scientific) FROM specimens",
        "host species",
    ),
    (
        "Macrosamples",
        "SELECT COUNT(*) FROM macrosamples",
        "SELECT COUNT(*) FROM macrosamples WHERE COALESCE(ena_accession, '') <> ''",
        "with an ENA accession",
    ),
    (
        "Cryosections",
        "SELECT COUNT(*) FROM cryosections",
        "SELECT COUNT(*) FROM cryosections WHERE has_image = 1",
        "with an image",
    ),
    (
        "Microsamples",
        "SELECT COUNT(*) FROM microsamples",
        "SELECT COUNT(*) FROM microsample_sequencing",
        "sequenced",
    ),
    (
        "Genomes",
        "SELECT COUNT(*) FROM genome_metadata",
        "SELECT COUNT(DISTINCT genome) FROM genome_metadata",
        "distinct genome IDs",
    ),
    (
        "Counts",
        "SELECT (SELECT COUNT(*) FROM macro_genome_counts) "
        "+ (SELECT COUNT(*) FROM microsample_counts)",
        "SELECT COUNT(*) FROM source_files WHERE kind = 'csv_matrix'",
        "matrices, zeros dropped",
    ),
)


def _catalog_summary(catalog_path: Path) -> list[tuple[str, str, str]]:
    """Summarise each level for the no-args overview table."""
    connection = connect(catalog_path)
    try:

        def scalar(sql: str) -> int:
            row = connection.execute(sql).fetchone()
            return int(row[0] or 0)

        return [
            (level, f"{scalar(total_sql):,}", f"{scalar(detail_sql):,} {suffix}")
            for level, total_sql, detail_sql, suffix in _SUMMARY_QUERIES
        ]
    finally:
        connection.close()


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{size} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _print_root_header(console: Console) -> None:
    console.print(Panel.fit(f"[bold]{ROOT_TITLE}[/bold]", border_style="cyan"))
    console.print(ROOT_DESCRIPTION)


def _render_root_header_text() -> str:
    console = Console(record=True, color_system=None, force_terminal=False, width=80)
    _print_root_header(console)
    return console.export_text().rstrip()


if __name__ == "__main__":
    app()
