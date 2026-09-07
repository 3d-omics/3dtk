"""Build one Typer sub-app per target from the declared filter specifications.

Every target gets the same action grammar -- ``query``, ``values``, ``stats``,
``fields``, and ``fetch`` where the records resolve to downloadable files -- so
a user who knows one target can drive the others. Generating the commands from
:mod:`threedtk.filters` is what keeps that promise true by construction rather
than by seven copies staying in sync by hand.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Optional

from rich.console import Console
import typer

from threedtk.fields import value_field_rows
from threedtk.filters import FILTERS, filter_key
from threedtk.output import render_or_export_rows, validate_export_options
from threedtk.query import (
    DEFAULT_QUERY_LIMIT,
    QueryValidationError,
    TARGETS,
    catalog_path_from_context,
    headers_for,
    query_rows,
)
from threedtk.stats import render_target_stats
from threedtk.values import DEFAULT_VALUES_LIMIT, value_rows

_DB_HELP = (
    "Path to an alternate SQLite catalogue. Defaults to the resolved catalogue."
)
_WHERE_HELP = "Advanced SQL predicate appended to the WHERE clause after validation."


def _parameter(
    name: str,
    annotation: Any,
    default: Any,
) -> inspect.Parameter:
    return inspect.Parameter(
        name,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=annotation,
        default=default,
    )


def _filter_parameters(target: str) -> list[inspect.Parameter]:
    parameters = []
    for option in FILTERS[target]:
        if option.type is bool:
            declaration = option.decls or (f"--{option.name.replace('_', '-')}",)
            parameters.append(
                _parameter(
                    option.name,
                    Optional[bool],
                    typer.Option(None, *declaration, help=option.help),
                )
            )
        else:
            parameters.append(
                _parameter(
                    option.name,
                    Optional[option.type],
                    typer.Option(None, *option.decls, help=option.help),
                )
            )
    return parameters


def _export_parameters(noun: str) -> list[inspect.Parameter]:
    return [
        _parameter(
            "csv",
            bool,
            typer.Option(False, "--csv", help=f"Write {noun} as CSV to stdout, or to --output-file."),
        ),
        _parameter(
            "tsv",
            bool,
            typer.Option(False, "--tsv", help=f"Write {noun} as TSV to stdout, or to --output-file."),
        ),
        _parameter(
            "output_file",
            Optional[Path],
            typer.Option(None, "--output-file", help="Write CSV or TSV output to this file instead of stdout."),
        ),
    ]


def _db_parameter() -> inspect.Parameter:
    return _parameter("db", Optional[Path], typer.Option(None, "--db", help=_DB_HELP))


def _where_parameter() -> inspect.Parameter:
    return _parameter("where", Optional[str], typer.Option(None, help=_WHERE_HELP))


def _bind(
    function: Callable[..., None],
    parameters: list[inspect.Parameter],
    *,
    name: str,
    doc: str,
) -> Callable[..., None]:
    """Give a ``**kwargs`` implementation an explicit signature for Typer."""
    function.__name__ = name
    function.__doc__ = doc
    function.__signature__ = inspect.Signature(parameters)
    function.__annotations__ = {
        parameter.name: parameter.annotation for parameter in parameters
    }
    return function


def _collect_filters(target: str, values: dict[str, Any]) -> dict[str, Any]:
    return {
        filter_key(option.name): values.get(option.name) for option in FILTERS[target]
    }


def _bad_parameter(exc: QueryValidationError, default_hint: str) -> typer.BadParameter:
    message = str(exc).lower()
    if "column" in message:
        hint = "--columns"
    elif "field" in message:
        hint = "--field"
    elif "limit" in message:
        hint = "--limit"
    else:
        hint = default_hint
    return typer.BadParameter(str(exc), param_hint=hint)


def build_target_app(target: str) -> typer.Typer:
    """Build the Typer sub-app for one target."""
    config = TARGETS[target]
    label = config.label
    title = label.capitalize()

    app = typer.Typer(
        help=f"Query, summarise, and export {label}.",
        no_args_is_help=True,
    )

    # ---- query -----------------------------------------------------------
    def _query(**values: Any) -> None:
        console = Console()
        validate_export_options(values["csv"], values["tsv"], values["output_file"])
        try:
            rows = query_rows(
                catalog_path_from_context(values["ctx"], values["db"]),
                target,
                filters=_collect_filters(target, values),
                where=values["where"],
                limit=values["limit"],
                columns=values["columns"],
            )
            headers = headers_for(target, columns=values["columns"])
        except QueryValidationError as exc:
            raise _bad_parameter(exc, "--where") from exc

        render_or_export_rows(
            console,
            headers,
            rows,
            title=title,
            csv_output=values["csv"],
            tsv_output=values["tsv"],
            output_file=values["output_file"],
        )

    app.command("query", help=f"List {label} matching the given filters.")(
        _bind(
            _query,
            [
                _parameter("ctx", typer.Context, inspect.Parameter.empty),
                _db_parameter(),
                *_filter_parameters(target),
                _where_parameter(),
                _parameter(
                    "limit",
                    int,
                    typer.Option(DEFAULT_QUERY_LIMIT, min=1, help="Maximum number of rows to print."),
                ),
                _parameter(
                    "columns",
                    Optional[str],
                    typer.Option(
                        None,
                        "--columns",
                        help="Columns to include: a preset name, 'all', or a comma-separated list.",
                    ),
                ),
                *_export_parameters("query results"),
            ],
            name="query",
            doc=f"List {label} matching the given filters.",
        )
    )

    # ---- values ----------------------------------------------------------
    def _values(**values: Any) -> None:
        console = Console()
        validate_export_options(values["csv"], values["tsv"], values["output_file"])
        try:
            resolved_field, rows = value_rows(
                str(catalog_path_from_context(values["ctx"], values["db"])),
                target=target,
                field=values["field"],
                filters=_collect_filters(target, values),
                where=values["where"],
                limit=values["limit"],
            )
        except QueryValidationError as exc:
            raise _bad_parameter(exc, "--field") from exc

        render_or_export_rows(
            console,
            ("value", "count"),
            rows,
            title=f"Values for {resolved_field}",
            csv_output=values["csv"],
            tsv_output=values["tsv"],
            output_file=values["output_file"],
        )

    app.command("values", help=f"Count distinct values of one {label[:-1]} field.")(
        _bind(
            _values,
            [
                _parameter("ctx", typer.Context, inspect.Parameter.empty),
                _db_parameter(),
                _parameter(
                    "field",
                    str,
                    typer.Option(..., "--field", help="Field to summarise with distinct values and counts."),
                ),
                *_filter_parameters(target),
                _where_parameter(),
                _parameter(
                    "limit",
                    int,
                    typer.Option(DEFAULT_VALUES_LIMIT, min=1, help="Maximum number of distinct values to print."),
                ),
                *_export_parameters("value counts"),
            ],
            name="values",
            doc=f"Count distinct values of one {label[:-1]} field, after filters.",
        )
    )

    # ---- stats -----------------------------------------------------------
    def _stats(**values: Any) -> None:
        try:
            render_target_stats(
                Console(),
                catalog_path=str(catalog_path_from_context(values["ctx"], values["db"])),
                target=target,
                filters=_collect_filters(target, values),
                where=values["where"],
            )
        except QueryValidationError as exc:
            raise _bad_parameter(exc, "--where") from exc

    app.command("stats", help=f"Summarise matching {label}.")(
        _bind(
            _stats,
            [
                _parameter("ctx", typer.Context, inspect.Parameter.empty),
                _db_parameter(),
                *_filter_parameters(target),
                _where_parameter(),
            ],
            name="stats",
            doc=f"Summarise matching {label} with headline figures and breakdowns.",
        )
    )

    # ---- fields ----------------------------------------------------------
    def _fields(**values: Any) -> None:
        render_or_export_rows(
            Console(),
            ("field", "type", "resolves_to"),
            value_field_rows(target),
            title=f"{title} value fields",
            csv_output=values["csv"],
            tsv_output=values["tsv"],
            output_file=values["output_file"],
        )

    app.command("fields", help=f"List fields accepted by {target} values --field.")(
        _bind(
            _fields,
            _export_parameters("fields"),
            name="fields",
            doc=f"List the fields accepted by ``{target} values --field``.",
        )
    )

    return app


def add_fetch_command(app: typer.Typer, target: str) -> typer.Typer:
    """Add ``fetch`` to a target whose records resolve to ENA files."""
    from threedtk.download import download_jobs, write_batch_script
    from threedtk.fetch import format_bytes, plan_fetch
    from threedtk.manifest import ManifestEntry, append_manifest_entry
    from threedtk.terms import ensure_terms_accepted

    label = TARGETS[target].label
    singular = label[:-1]

    _REASON_MESSAGES = {
        "no_accession": "no ENA accession recorded",
        "unresolved_accession": "accession not found in the ENA Portal API",
        "metabolights": "metabolomics data, published to MetaboLights",
    }

    def _fetch(**values: Any) -> None:
        console = Console()
        try:
            plan = plan_fetch(
                catalog_path_from_context(values["ctx"], values["db"]),
                target,
                filters=_collect_filters(target, values),
                where=values["where"],
                limit=values["limit"],
                output_dir=values["output_dir"],
                protocol=values["protocol"],
                progress=console.print,
            )
        except QueryValidationError as exc:
            raise _bad_parameter(exc, "--where") from exc

        if plan.matched_count == 0:
            console.print(f"No matching {label} found.")
            return

        console.print(
            f"Matched {plan.matched_count:,} {label}; queued {len(plan.jobs):,} files "
            f"({format_bytes(plan.total_bytes)})."
        )
        for reason, count in sorted(plan.reasons().items()):
            console.print(
                f"[yellow]{count:,}[/yellow] {label} skipped: "
                f"{_REASON_MESSAGES.get(reason, reason)}."
            )
        if metabolights := [
            record for record in plan.unfetchable if record.reason == "metabolights"
        ]:
            accessions = sorted({record.detail for record in metabolights if record.detail})
            console.print(
                "  MetaboLights accessions: " + ", ".join(accessions[:10])
                + (" ..." if len(accessions) > 10 else "")
            )

        manifest = values["manifest_path"]
        batch_mode = values["batch"] is not None

        def record_unfetchable() -> None:
            """Log skipped records, so the manifest accounts for every match."""
            for record in plan.unfetchable:
                append_manifest_entry(
                    manifest,
                    ManifestEntry(
                        entry_type=singular,
                        id_field=f"{singular}_id",
                        id_value=record.record_id,
                        url=None,
                        path=None,
                        checksum=None,
                        status=record.reason,
                    ),
                )

        if not plan.jobs:
            # Nothing to download, so no terms prompt -- but the matched records
            # that could not be fetched are still worth recording.
            if not batch_mode:
                record_unfetchable()
            return

        ensure_terms_accepted(console, accept_terms=values["accept_terms"])

        if batch_mode:
            script_path = write_batch_script(
                values["batch"], list(plan.jobs), overwrite=values["overwrite"]
            )
            console.print(
                f"Wrote batch download script with {len(plan.jobs):,} files to {script_path}."
            )
            return

        record_unfetchable()
        results = download_jobs(
            list(plan.jobs),
            manifest_path=manifest,
            overwrite=values["overwrite"],
            console=console,
        )
        counts: dict[str, int] = {}
        for result in results:
            counts[result.status] = counts.get(result.status, 0) + 1
        console.print(
            "Download summary: "
            + ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
        )

    app.command(
        "fetch",
        help=f"Download FASTQ files for matching {label}, or write a batch script.",
    )(
        _bind(
            _fetch,
            [
                _parameter("ctx", typer.Context, inspect.Parameter.empty),
                _db_parameter(),
                *_filter_parameters(target),
                _where_parameter(),
                _parameter(
                    "limit",
                    Optional[int],
                    typer.Option(None, min=1, help=f"Maximum number of {label} to fetch."),
                ),
                _parameter(
                    "output_dir",
                    Path,
                    typer.Option(Path("downloads"), help="Base output directory for downloaded files."),
                ),
                _parameter(
                    "protocol",
                    str,
                    typer.Option("https", help="URL scheme for ENA downloads: https or ftp."),
                ),
                _parameter(
                    "batch",
                    Optional[Path],
                    typer.Option(
                        None,
                        "--batch",
                        "--script",
                        help="Write a shell script of download commands instead of downloading now.",
                    ),
                ),
                _parameter(
                    "manifest_path",
                    Path,
                    typer.Option(Path("manifest.jsonl"), help="Path to the append-only download manifest."),
                ),
                _parameter(
                    "accept_terms",
                    bool,
                    typer.Option(False, "--accept-terms", help="Skip the data usage terms prompt."),
                ),
                _parameter(
                    "overwrite",
                    bool,
                    typer.Option(False, "--overwrite", help="Overwrite existing files instead of skipping them."),
                ),
            ],
            name="fetch",
            doc=f"Download FASTQ files for matching {label}.",
        )
    )
    return app


def add_counts_commands(app: typer.Typer) -> typer.Typer:
    """Add ``matrices`` and ``export`` to the counts sub-app.

    ``export`` is the capability ``ehitk`` has no equivalent of: it rebuilds a
    dense genome x sample matrix from the sparse tables, restoring the dropped
    zeros and following the original axis order recorded in ``matrix_axes``.
    """
    from threedtk.counts import CountsError, dense_matrix, list_matrix_sources, sample_coordinates

    def _matrices(**values: Any) -> None:
        console = Console()
        catalog = catalog_path_from_context(values["ctx"], values["db"])
        try:
            sources = list_matrix_sources(
                catalog,
                level=values["level"],
                experiment_id=values["experiment_id"],
                cryosection_id=values["cryosection_id"],
                source_id=values["source_id"],
            )
        except QueryValidationError as exc:
            raise _bad_parameter(exc, "--level") from exc

        rows = [
            {
                "level": source.level,
                "owner": source.owner_value,
                "filename": source.filename,
                "genomes": len(source.genomes),
                "samples": len(source.samples),
                "non_zero": source.declared_cells,
                "dense_cells": source.dense_cells,
                "source_id": source.source_id,
            }
            for source in sources
        ]
        render_or_export_rows(
            console,
            ("level", "owner", "filename", "genomes", "samples", "non_zero", "dense_cells", "source_id"),
            rows,
            title="Count matrices",
            csv_output=values["csv"],
            tsv_output=values["tsv"],
            output_file=values["output_file"],
        )

    app.command("matrices", help="List the available count matrices.")(
        _bind(
            _matrices,
            [
                _parameter("ctx", typer.Context, inspect.Parameter.empty),
                _db_parameter(),
                _parameter("level", Optional[str], typer.Option(None, help="Count level: macro or micro.")),
                _parameter("experiment_id", Optional[str], typer.Option(None, help="Restrict to one experiment.")),
                _parameter("cryosection_id", Optional[str], typer.Option(None, help="Restrict to one cryosection.")),
                _parameter("source_id", Optional[str], typer.Option(None, help="Select one matrix by source id.")),
                *_export_parameters("matrix listings"),
            ],
            name="matrices",
            doc="List the count matrices recorded in the catalogue.",
        )
    )

    def _export(**values: Any) -> None:
        console = Console()
        catalog = catalog_path_from_context(values["ctx"], values["db"])
        try:
            sources = list_matrix_sources(
                catalog,
                level=values["level"],
                experiment_id=values["experiment_id"],
                cryosection_id=values["cryosection_id"],
                source_id=values["source_id"],
            )
            taxonomy = {
                rank: values.get(key)
                for rank, key in (
                    ("domain", "domain"),
                    ("phylum", "phylum"),
                    ("class", "class_"),
                    ("order", "order"),
                    ("family", "family"),
                    ("genus", "genus"),
                    ("species", "species"),
                )
            }
            matrix = dense_matrix(
                catalog,
                sources,
                genomes=_split(values["genome"]),
                samples=_split(values["sample"]),
                taxonomy=taxonomy,
            )
            matrix.verify()
        except (CountsError, QueryValidationError) as exc:
            raise typer.BadParameter(str(exc), param_hint="--experiment-id") from exc

        if not matrix.genomes or not matrix.samples:
            console.print("No count cells matched the given selectors.")
            return

        if values["long"]:
            headers = ("genome", "sample", "count")
            rows = list(matrix.long_rows(include_zeros=values["include_zeros"]))
        else:
            headers = matrix.headers()
            rows = list(matrix.rows())

        if not (values["csv"] or values["tsv"]):
            console.print(
                f"Rebuilt {len(matrix.genomes):,} genomes x {len(matrix.samples):,} samples "
                f"from {len(matrix.sources)} matrix/matrices "
                f"({matrix.non_zero_cells:,} non-zero cells restored to "
                f"{len(matrix.genomes) * len(matrix.samples):,} dense cells)."
            )

        render_or_export_rows(
            console,
            headers,
            rows,
            title="Counts",
            csv_output=values["csv"],
            tsv_output=values["tsv"],
            output_file=values["output_file"],
        )

        if values["coordinates"] is not None:
            level = matrix.sources[0].level
            coordinate_rows = sample_coordinates(catalog, matrix.samples, level=level)
            headers = tuple(coordinate_rows[0]) if coordinate_rows else ("sample",)
            render_or_export_rows(
                console,
                headers,
                coordinate_rows,
                title="Sample coordinates",
                csv_output=not values["tsv"],
                tsv_output=values["tsv"],
                output_file=values["coordinates"],
            )

    app.command(
        "export",
        help="Rebuild a dense genome x sample count matrix, restoring dropped zeros.",
    )(
        _bind(
            _export,
            [
                _parameter("ctx", typer.Context, inspect.Parameter.empty),
                _db_parameter(),
                _parameter("level", Optional[str], typer.Option(None, help="Count level: macro or micro.")),
                _parameter("experiment_id", Optional[str], typer.Option(None, help="Export this experiment's matrices.")),
                _parameter("cryosection_id", Optional[str], typer.Option(None, help="Export this cryosection's matrix.")),
                _parameter("source_id", Optional[str], typer.Option(None, help="Export one matrix by source id.")),
                _parameter("genome", Optional[str], typer.Option(None, help="Restrict rows to these genome IDs.")),
                _parameter("sample", Optional[str], typer.Option(None, help="Restrict columns to these sample IDs.")),
                _parameter("domain", Optional[str], typer.Option(None, help="Restrict rows to this GTDB domain.")),
                _parameter("phylum", Optional[str], typer.Option(None, help="Restrict rows to this GTDB phylum.")),
                _parameter("class_", Optional[str], typer.Option(None, "--class", help="Restrict rows to this GTDB class.")),
                _parameter("order", Optional[str], typer.Option(None, help="Restrict rows to this GTDB order.")),
                _parameter("family", Optional[str], typer.Option(None, help="Restrict rows to this GTDB family.")),
                _parameter("genus", Optional[str], typer.Option(None, help="Restrict rows to this GTDB genus.")),
                _parameter("species", Optional[str], typer.Option(None, help="Restrict rows to this GTDB species.")),
                _parameter(
                    "long",
                    bool,
                    typer.Option(False, "--long", help="Emit tidy genome/sample/count rows instead of a wide matrix."),
                ),
                _parameter(
                    "include_zeros",
                    bool,
                    typer.Option(False, "--include-zeros", help="With --long, also emit the restored zero cells."),
                ),
                _parameter(
                    "coordinates",
                    Optional[Path],
                    typer.Option(
                        None,
                        "--coordinates",
                        help="Also write a sample coordinate table, aligned to the matrix columns.",
                    ),
                ),
                *_export_parameters("the matrix"),
            ],
            name="export",
            doc="Rebuild a dense genome x sample count matrix.",
        )
    )
    return app


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]
