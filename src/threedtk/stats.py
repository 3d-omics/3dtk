"""Per-target summaries with top-N breakdowns.

Like the query engine, each target's statistics are *declared* rather than
hand-written: a :class:`StatsSpec` names the aggregate expressions, the labels
to present them under, and the breakdowns to group by. Adding a metric is a
registry edit.

A label key ending in ``_range`` is rendered from three summary keys
(``avg_``/``min_``/``max_`` + the stem), so ranges cost one declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any, Mapping

from rich.console import Console
from rich.table import Table

from threedtk.query import (
    GENOME_QUALITY_CASE_EXPR,
    build_filtered_source_query,
    connect,
    resolve_catalog_path,
)

TOP_BREAKDOWN_ROWS = 5


@dataclass(frozen=True, slots=True)
class StatBreakdown:
    """One named breakdown table within a :class:`TargetStats` result.

    Attributes:
        title: Human-readable breakdown title.
        value_header: Header label for the grouping value column.
        rows: Breakdown rows as dictionaries keyed by column name.
    """

    title: str
    value_header: str
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class TargetStats:
    """Summary statistics for a queried target.

    Attributes:
        target: The target the statistics describe.
        title: Human-readable title for the statistics block.
        summary: Raw summary metrics keyed by name.
        summary_labels: Ordered ``(label, key)`` pairs for presentation.
        breakdowns: Named breakdown tables.
        empty_message: Message shown when nothing matched, if any.
    """

    target: str
    title: str
    summary: dict[str, Any]
    summary_labels: tuple[tuple[str, str], ...]
    breakdowns: tuple[StatBreakdown, ...]
    empty_message: str | None = None


@dataclass(frozen=True)
class BreakdownSpec:
    title: str
    header: str
    expression: str
    limit: int = TOP_BREAKDOWN_ROWS


@dataclass(frozen=True)
class StatsSpec:
    title: str
    matched_key: str
    aggregates: tuple[str, ...]
    summary_labels: tuple[tuple[str, str], ...]
    breakdowns: tuple[BreakdownSpec, ...]
    empty_message: str


def _range_aggregates(column: str, stem: str) -> tuple[str, ...]:
    return (
        f'AVG("{column}") AS avg_{stem}',
        f'MIN("{column}") AS min_{stem}',
        f'MAX("{column}") AS max_{stem}',
    )


def _non_empty(column: str, alias: str) -> str:
    return (
        f'SUM(CASE WHEN "{column}" IS NOT NULL AND "{column}" <> \'\' '
        f"THEN 1 ELSE 0 END) AS {alias}"
    )


STATS: dict[str, StatsSpec] = {
    "experiments": StatsSpec(
        title="Experiment Stats",
        matched_key="matched_experiments",
        aggregates=(
            "COUNT(*) AS matched_experiments",
            'COUNT(DISTINCT "experiment_type") AS distinct_types',
            'SUM(COALESCE("has_genome_catalogue", 0)) AS with_genome_catalogue',
            'SUM(COALESCE("mag_count", 0)) AS total_mags',
            *_range_aggregates("mag_completeness_avg", "completeness"),
        ),
        summary_labels=(
            ("Matched experiments", "matched_experiments"),
            ("Distinct types", "distinct_types"),
            ("With genome catalogue", "with_genome_catalogue"),
            ("Total MAGs", "total_mags"),
            ("MAG completeness (avg/min/max)", "completeness_range"),
        ),
        breakdowns=(
            BreakdownSpec("Experiment types", "experiment_type", '"experiment_type"'),
        ),
        empty_message="No matching experiments found.",
    ),
    "specimens": StatsSpec(
        title="Specimen Stats",
        matched_key="matched_specimens",
        aggregates=(
            "COUNT(*) AS matched_specimens",
            'COUNT(DISTINCT "experiment_id") AS distinct_experiments',
            'COUNT(DISTINCT "species_scientific") AS distinct_species',
            'COUNT(DISTINCT "treatment_name") AS distinct_treatments',
            'COUNT(DISTINCT "pen") AS distinct_pens',
            _non_empty("biosample_accession", "with_biosample"),
            *_range_aggregates("weight", "weight"),
        ),
        summary_labels=(
            ("Matched specimens", "matched_specimens"),
            ("Distinct experiments", "distinct_experiments"),
            ("Distinct host species", "distinct_species"),
            ("Distinct treatments", "distinct_treatments"),
            ("Distinct pens", "distinct_pens"),
            ("With BioSample accession", "with_biosample"),
            ("Weight (avg/min/max)", "weight_range"),
        ),
        breakdowns=(
            BreakdownSpec("Top host species", "species_scientific", '"species_scientific"'),
            # treatment_group holds unresolved Airtable record ids, so group by
            # the human-readable name instead. See docs/database.rst.
            BreakdownSpec("Treatments", "treatment_name", '"treatment_name"'),
            BreakdownSpec("Sex distribution", "sex", '"sex"', limit=10),
        ),
        empty_message="No matching specimens found.",
    ),
    "macrosamples": StatsSpec(
        title="Macrosample Stats",
        matched_key="matched_macrosamples",
        aggregates=(
            "COUNT(*) AS matched_macrosamples",
            'COUNT(DISTINCT "specimen_id") AS distinct_specimens',
            'COUNT(DISTINCT "experiment_id") AS distinct_experiments',
            'COUNT(DISTINCT "sample_type") AS distinct_sample_types',
            _non_empty("ena_accession", "with_ena"),
            _non_empty("metabolights_accession", "with_metabolights"),
            _non_empty("library_id", "with_library"),
        ),
        summary_labels=(
            ("Matched macrosamples", "matched_macrosamples"),
            ("Distinct specimens", "distinct_specimens"),
            ("Distinct experiments", "distinct_experiments"),
            ("Distinct sample types", "distinct_sample_types"),
            ("With ENA accession", "with_ena"),
            ("With MetaboLights accession", "with_metabolights"),
            ("With sequencing library", "with_library"),
        ),
        breakdowns=(
            BreakdownSpec("Data types", "data_type", '"data_type"'),
            BreakdownSpec("Top sample types", "sample_type", '"sample_type"'),
            BreakdownSpec("Preservatives", "preservative", '"preservative"'),
        ),
        empty_message="No matching macrosamples found.",
    ),
    "cryosections": StatsSpec(
        title="Cryosection Stats",
        matched_key="matched_cryosections",
        aggregates=(
            "COUNT(*) AS matched_cryosections",
            'COUNT(DISTINCT "macrosample_id") AS distinct_macrosamples',
            'COUNT(DISTINCT "specimen_id") AS distinct_specimens',
            'SUM(COALESCE("has_image", 0)) AS with_image',
            'SUM(COALESCE("microsample_count", 0)) AS total_microsamples',
            *_range_aggregates("microsample_count", "microsamples"),
        ),
        summary_labels=(
            ("Matched cryosections", "matched_cryosections"),
            ("Distinct macrosamples", "distinct_macrosamples"),
            ("Distinct specimens", "distinct_specimens"),
            ("With image", "with_image"),
            ("Declared microsamples (total)", "total_microsamples"),
            ("Microsamples per section (avg/min/max)", "microsamples_range"),
        ),
        breakdowns=(
            BreakdownSpec("Positions", "position", '"position"'),
            BreakdownSpec("Top sample types", "sample_type", '"sample_type"'),
        ),
        empty_message="No matching cryosections found.",
    ),
    "microsamples": StatsSpec(
        title="Microsample Stats",
        matched_key="matched_microsamples",
        aggregates=(
            "COUNT(*) AS matched_microsamples",
            'COUNT(DISTINCT "cryosection_id") AS distinct_cryosections',
            'COUNT(DISTINCT "specimen_id") AS distinct_specimens',
            'COUNT(DISTINCT "experiment_id") AS distinct_experiments',
            _non_empty("run_accession", "with_sequencing"),
            'SUM(CASE WHEN "x_coord" IS NOT NULL AND "y_coord" IS NOT NULL '
            "THEN 1 ELSE 0 END) AS with_coordinates",
            *_range_aggregates("size", "size"),
            *_range_aggregates("x_coord", "x"),
            *_range_aggregates("y_coord", "y"),
        ),
        summary_labels=(
            ("Matched microsamples", "matched_microsamples"),
            ("Distinct cryosections", "distinct_cryosections"),
            ("Distinct specimens", "distinct_specimens"),
            ("Distinct experiments", "distinct_experiments"),
            ("With sequencing run", "with_sequencing"),
            ("With spatial coordinates", "with_coordinates"),
            ("Size (avg/min/max)", "size_range"),
            ("x_coord (avg/min/max)", "x_range"),
            ("y_coord (avg/min/max)", "y_range"),
        ),
        breakdowns=(
            BreakdownSpec("Top sample types", "sample_type", '"sample_type"'),
            BreakdownSpec("Collection methods", "collection_method", '"collection_method"'),
            BreakdownSpec("Top cryosections", "cryosection_id", '"cryosection_id"'),
        ),
        empty_message="No matching microsamples found.",
    ),
    "genomes": StatsSpec(
        title="Genome Stats",
        matched_key="matched_genomes",
        aggregates=(
            "COUNT(*) AS matched_genomes",
            'COUNT(DISTINCT "genome") AS distinct_genomes',
            'COUNT(DISTINCT "experiment_id") AS distinct_experiments',
            'COUNT(DISTINCT "phylum") AS distinct_phyla',
            'COUNT(DISTINCT "species") AS distinct_species',
            *_range_aggregates("completeness", "completeness"),
            *_range_aggregates("contamination", "contamination"),
            *_range_aggregates("length", "length"),
        ),
        summary_labels=(
            ("Matched genomes", "matched_genomes"),
            ("Distinct genome IDs", "distinct_genomes"),
            ("Distinct experiments", "distinct_experiments"),
            ("Distinct phyla", "distinct_phyla"),
            ("Distinct species", "distinct_species"),
            ("Completeness (avg/min/max)", "completeness_range"),
            ("Contamination (avg/min/max)", "contamination_range"),
            ("Length (avg/min/max)", "length_range"),
        ),
        breakdowns=(
            BreakdownSpec("Quality distribution", "quality", GENOME_QUALITY_CASE_EXPR, limit=3),
            BreakdownSpec("Top phyla", "phylum", '"phylum"'),
            BreakdownSpec("Top genera", "genus", '"genus"'),
        ),
        empty_message="No matching genomes found.",
    ),
    "counts": StatsSpec(
        title="Count Stats",
        matched_key="matched_cells",
        aggregates=(
            "COUNT(*) AS matched_cells",
            'COUNT(DISTINCT "genome") AS distinct_genomes',
            'COUNT(DISTINCT "sample") AS distinct_samples',
            'COUNT(DISTINCT "source_id") AS distinct_matrices',
            'COUNT(DISTINCT "experiment_id") AS distinct_experiments',
            'SUM(CASE WHEN "x_coord" IS NOT NULL THEN 1 ELSE 0 END) AS with_coordinates',
            'SUM("count") AS total_count',
            *_range_aggregates("count", "count"),
        ),
        summary_labels=(
            ("Matched non-zero cells", "matched_cells"),
            ("Distinct genomes", "distinct_genomes"),
            ("Distinct samples", "distinct_samples"),
            ("Distinct source matrices", "distinct_matrices"),
            ("Distinct experiments", "distinct_experiments"),
            ("Cells with spatial coordinates", "with_coordinates"),
            ("Summed count", "total_count"),
            ("Count per cell (avg/min/max)", "count_range"),
        ),
        breakdowns=(
            BreakdownSpec("Levels", "level", '"level"', limit=2),
            BreakdownSpec("Top phyla", "phylum", '"phylum"'),
            BreakdownSpec("Top genera", "genus", '"genus"'),
        ),
        empty_message="No matching counts found.",
    ),
}


def target_stats(
    *,
    catalog_path: str,
    target: str,
    filters: Mapping[str, Any] | None = None,
    where: str | None = None,
) -> TargetStats:
    """Compute summary statistics and breakdowns for matching records."""
    if target not in STATS:
        raise ValueError(f"Unsupported stats target: {target}")
    spec = STATS[target]
    resolved = resolve_catalog_path(catalog_path)
    base_sql, parameters = build_filtered_source_query(
        target, filters=filters, where=where
    )

    connection = connect(resolved)
    try:
        summary = connection.execute(
            f"SELECT {', '.join(spec.aggregates)} FROM ({base_sql}) AS filtered",
            parameters,
        ).fetchone()
        summary_dict = dict(summary)

        if not summary_dict[spec.matched_key]:
            return TargetStats(
                target=target,
                title=spec.title,
                summary=summary_dict,
                summary_labels=(),
                breakdowns=(),
                empty_message=spec.empty_message,
            )

        breakdowns = tuple(
            StatBreakdown(
                title=breakdown.title,
                value_header=breakdown.header,
                rows=tuple(
                    dict(row)
                    for row in _top_counts(
                        connection, base_sql, parameters, breakdown
                    )
                ),
            )
            for breakdown in spec.breakdowns
        )
    finally:
        connection.close()

    return TargetStats(
        target=target,
        title=spec.title,
        summary=summary_dict,
        summary_labels=spec.summary_labels,
        breakdowns=breakdowns,
    )


def render_target_stats(
    console: Console,
    *,
    catalog_path: str,
    target: str,
    filters: Mapping[str, Any] | None = None,
    where: str | None = None,
) -> None:
    """Compute and print statistics for a target."""
    _render_stats(
        console,
        target_stats(
            catalog_path=catalog_path, target=target, filters=filters, where=where
        ),
    )


def _top_counts(
    connection: sqlite3.Connection,
    base_sql: str,
    parameters: list[Any],
    breakdown: BreakdownSpec,
) -> list[sqlite3.Row]:
    return connection.execute(
        f"""
        SELECT
            COALESCE(NULLIF(CAST({breakdown.expression} AS TEXT), ''), '<missing>') AS value,
            COUNT(*) AS count
        FROM ({base_sql}) AS filtered
        GROUP BY value
        ORDER BY count DESC, value ASC
        LIMIT ?
        """,
        [*parameters, breakdown.limit],
    ).fetchall()


def _render_stats(console: Console, stats: TargetStats) -> None:
    if stats.empty_message is not None:
        console.print(stats.empty_message)
        return

    console.print(f"[bold]{stats.title}[/bold]")
    for label, key in stats.summary_labels:
        console.print(f"{label}: {_format_summary_value(stats.summary, key)}")

    for breakdown in stats.breakdowns:
        if not breakdown.rows:
            continue
        table = Table(title=breakdown.title)
        table.add_column(breakdown.value_header)
        table.add_column("count", justify="right")
        for row in breakdown.rows:
            table.add_row(str(row["value"]), f"{row['count']:,}")
        console.print(table)


def _format_summary_value(summary: Mapping[str, Any], key: str) -> str:
    if key.endswith("_range"):
        stem = key[: -len("_range")]
        return _format_range(
            summary.get(f"avg_{stem}"),
            summary.get(f"min_{stem}"),
            summary.get(f"max_{stem}"),
        )
    value = summary.get(key)
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _format_range(avg_value: Any, min_value: Any, max_value: Any) -> str:
    if avg_value is None or min_value is None or max_value is None:
        return "n/a"
    return f"{avg_value:,.2f} / {min_value:,.2f} / {max_value:,.2f}"
