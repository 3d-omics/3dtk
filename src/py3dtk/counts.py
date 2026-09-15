"""Dense reconstruction of the sparse genome x sample count matrices.

The catalogue stores counts sparsely -- zeros are dropped, which is about
five-sixths of the microsample cells. Rebuilding the dense matrix therefore
cannot use ``SELECT DISTINCT`` over the sparse rows: a genome or a sample whose
entire row or column is zero would vanish, silently changing the matrix shape.

``matrix_axes`` preserves the row and column keys of every ingested matrix in
their original order, so it is the only correct source for the axes. This
module reads the axes from there, fills a zero matrix, and overlays the
non-zero cells. The invariant that makes this checkable is
``source_files.row_count == COUNT(*)`` of the sparse rows for that source; it
holds for all 82 matrices in the 2026.08.29 release.

Within one experiment every microsample matrix shares an identical genome axis,
so :func:`dense_matrix` can merge several cryosections into one wide matrix by
concatenating their sample columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from py3dtk.query import (
    QueryValidationError,
    TAXONOMY_PREFIXES,
    connect,
    resolve_catalog_path,
)

MACRO_TABLE = "macro_genome_counts"
MICRO_TABLE = "microsample_counts"
LEVEL_TABLES = {"macro": MACRO_TABLE, "micro": MICRO_TABLE}
TABLE_LEVELS = {table: level for level, table in LEVEL_TABLES.items()}

#: Sparse count tables key their sample column differently per level.
SAMPLE_COLUMNS = {MACRO_TABLE: "macrosample", MICRO_TABLE: "microsample"}


class CountsError(RuntimeError):
    """Raised when a counts export cannot be satisfied as requested."""


@dataclass(frozen=True)
class MatrixSource:
    """One ingested count matrix, as recorded in ``source_files``.

    Attributes:
        source_id: Catalogue-wide identifier of the source attachment.
        target_table: Sparse table the matrix was ingested into.
        level: ``"macro"`` or ``"micro"``.
        owner_column: Column naming the matrix's owner (experiment/cryosection).
        owner_value: The owning experiment or cryosection identifier.
        filename: Original CSV file name.
        declared_cells: ``source_files.row_count`` -- the non-zero cell count.
        genomes: Row axis keys, in original order.
        samples: Column axis keys, in original order.
        key_name: Header of the index column in the original CSV.
    """

    source_id: str
    target_table: str
    level: str
    owner_column: str
    owner_value: str
    filename: str
    declared_cells: int
    genomes: tuple[str, ...]
    samples: tuple[str, ...]
    key_name: str = "genome"

    @property
    def dense_cells(self) -> int:
        """Number of cells the fully dense matrix holds."""
        return len(self.genomes) * len(self.samples)


@dataclass(frozen=True)
class DenseMatrix:
    """A rebuilt dense matrix and the provenance needed to check it.

    Attributes:
        key_name: Name of the index column (``"genome"``).
        genomes: Row keys in matrix order.
        samples: Column keys in matrix order.
        values: ``(genome, sample) -> count`` for non-zero cells only.
        sources: The matrix sources this was assembled from.
        non_zero_cells: Number of non-zero cells actually loaded.
        declared_cells: Sum of ``source_files.row_count`` over those sources.
    """

    key_name: str
    genomes: tuple[str, ...]
    samples: tuple[str, ...]
    values: Mapping[tuple[str, str], float]
    sources: tuple[MatrixSource, ...]
    non_zero_cells: int
    declared_cells: int
    filtered: bool = field(default=False)

    def cell(self, genome: str, sample: str) -> float:
        """Return one cell, restoring a dropped zero as ``0``."""
        return self.values.get((genome, sample), 0)

    def headers(self) -> tuple[str, ...]:
        return (self.key_name, *self.samples)

    def rows(self) -> Iterator[dict[str, Any]]:
        """Yield the dense matrix one row at a time, zeros restored."""
        for genome in self.genomes:
            row: dict[str, Any] = {self.key_name: genome}
            for sample in self.samples:
                row[sample] = self.values.get((genome, sample), 0)
            yield row

    def long_rows(self, *, include_zeros: bool = False) -> Iterator[dict[str, Any]]:
        """Yield tidy ``(genome, sample, count)`` rows."""
        for genome in self.genomes:
            for sample in self.samples:
                value = self.values.get((genome, sample))
                if value is None and not include_zeros:
                    continue
                yield {
                    "genome": genome,
                    "sample": sample,
                    "count": 0 if value is None else value,
                }

    def verify(self) -> None:
        """Check the rebuilt matrix against the catalogue's own provenance.

        Raises:
            CountsError: If the number of non-zero cells loaded disagrees with
                ``source_files.row_count``. Only meaningful for an unfiltered
                export, where the two must be equal.
        """
        if self.filtered:
            return
        if self.non_zero_cells != self.declared_cells:
            raise CountsError(
                f"Round-trip check failed: loaded {self.non_zero_cells} non-zero "
                f"cells but source_files declares {self.declared_cells}."
            )


def list_matrix_sources(
    catalog_path: str | Path,
    *,
    level: str | None = None,
    experiment_id: str | None = None,
    cryosection_id: str | None = None,
    source_id: str | None = None,
) -> list[MatrixSource]:
    """List the count matrices matching the given selectors.

    Args:
        catalog_path: Catalogue to read.
        level: ``"macro"``, ``"micro"``, or ``None`` for both.
        experiment_id: Restrict to matrices belonging to this experiment. For
            microsample matrices the experiment is derived through
            ``cryosections -> macrosamples -> specimens``.
        cryosection_id: Restrict to microsample matrices for this cryosection.
        source_id: Select one matrix by its exact source identifier.

    Returns:
        Matching sources, ordered by level then owner.
    """
    if level is not None and level not in LEVEL_TABLES:
        raise QueryValidationError(
            f"Unknown counts level: {level}. Use 'macro' or 'micro'."
        )

    resolved = resolve_catalog_path(catalog_path)
    connection = connect(resolved)
    try:
        conditions = ["sf.kind = 'csv_matrix'"]
        parameters: list[Any] = []
        if level is not None:
            conditions.append("sf.target_table = ?")
            parameters.append(LEVEL_TABLES[level])
        if source_id is not None:
            conditions.append("sf.source_id = ?")
            parameters.append(source_id)
        if cryosection_id is not None:
            conditions.append(
                f"(sf.target_table = '{MICRO_TABLE}' AND LOWER(sf.owner_value) = LOWER(?))"
            )
            parameters.append(cryosection_id)
        if experiment_id is not None:
            conditions.append(
                f"""(
                    (sf.target_table = '{MACRO_TABLE}' AND LOWER(sf.owner_value) = LOWER(?))
                    OR (sf.target_table = '{MICRO_TABLE}' AND LOWER(COALESCE((
                        SELECT s."experiment_id" FROM "cryosections" AS c
                        LEFT JOIN "macrosamples" AS ma ON c."macrosample_id" = ma."macrosample_id"
                        LEFT JOIN "specimens" AS s ON ma."specimen_id" = s."specimen_id"
                        WHERE c."cryosection_id" = sf.owner_value
                    ), '')) = LOWER(?))
                )"""
            )
            parameters.extend([experiment_id, experiment_id])

        rows = connection.execute(
            f"""
            SELECT source_id, target_table, owner_column, owner_value, filename, row_count
            FROM source_files AS sf
            WHERE {' AND '.join(conditions)}
            ORDER BY target_table, owner_value
            """,
            parameters,
        ).fetchall()

        sources = []
        for row in rows:
            axes = _read_axes(connection, row["source_id"])
            sources.append(
                MatrixSource(
                    source_id=row["source_id"],
                    target_table=row["target_table"],
                    level=TABLE_LEVELS[row["target_table"]],
                    owner_column=row["owner_column"],
                    owner_value=row["owner_value"],
                    filename=row["filename"],
                    declared_cells=row["row_count"] or 0,
                    genomes=axes["row"],
                    samples=axes["column"],
                    key_name=(axes["key"] or ("genome",))[0],
                )
            )
        return sources
    finally:
        connection.close()


def _read_axes(connection, source_id: str) -> dict[str, tuple[str, ...]]:
    rows = connection.execute(
        "SELECT axis, key FROM matrix_axes WHERE source_id = ? ORDER BY axis, position",
        (source_id,),
    ).fetchall()
    axes: dict[str, list[str]] = {"row": [], "column": [], "key": []}
    for row in rows:
        axes.setdefault(row["axis"], []).append(row["key"])
    return {axis: tuple(keys) for axis, keys in axes.items()}


def dense_matrix(
    catalog_path: str | Path,
    sources: Sequence[MatrixSource],
    *,
    genomes: Sequence[str] | None = None,
    samples: Sequence[str] | None = None,
    taxonomy: Mapping[str, str] | None = None,
) -> DenseMatrix:
    """Rebuild one dense matrix from one or more sparse sources.

    Args:
        catalog_path: Catalogue to read.
        sources: Matrices to assemble. Multiple sources are merged by unioning
            the genome axis (in first-seen order) and concatenating sample
            columns, which is well-defined because matrices within an
            experiment share a genome axis.
        genomes: Restrict rows to these genome identifiers.
        samples: Restrict columns to these sample identifiers.
        taxonomy: Restrict rows by GTDB rank, e.g. ``{"genus": "Faeciplasma"}``.
            Prefixed and unprefixed values are both accepted.

    Returns:
        A :class:`DenseMatrix`. Axis order always follows ``matrix_axes``.

    Raises:
        CountsError: If no sources were given, or they mix levels.
    """
    if not sources:
        raise CountsError("No count matrices matched the given selectors.")
    levels = {source.level for source in sources}
    if len(levels) > 1:
        raise CountsError(
            "Cannot merge macro and micro matrices in one export; "
            "select a single level with --level."
        )

    resolved = resolve_catalog_path(catalog_path)
    connection = connect(resolved)
    try:
        genome_allow = _resolve_genome_filter(connection, sources, genomes, taxonomy)
        sample_allow = _casefold_set(samples)

        ordered_genomes: list[str] = []
        seen_genomes: set[str] = set()
        ordered_samples: list[str] = []
        seen_samples: set[str] = set()

        for source in sources:
            for genome in source.genomes:
                if genome in seen_genomes:
                    continue
                if genome_allow is not None and genome not in genome_allow:
                    continue
                seen_genomes.add(genome)
                ordered_genomes.append(genome)
            for sample in source.samples:
                if sample in seen_samples:
                    continue
                if sample_allow is not None and sample.lower() not in sample_allow:
                    continue
                seen_samples.add(sample)
                ordered_samples.append(sample)

        values: dict[tuple[str, str], float] = {}
        loaded = 0
        for source in sources:
            sample_column = SAMPLE_COLUMNS[source.target_table]
            rows = connection.execute(
                f'SELECT "genome", "{sample_column}" AS sample, "count" '
                f'FROM "{source.target_table}" WHERE source_id = ?',
                (source.source_id,),
            ).fetchall()
            loaded += len(rows)
            for row in rows:
                key = (row["genome"], row["sample"])
                if key[0] in seen_genomes and key[1] in seen_samples:
                    values[key] = row["count"]
    finally:
        connection.close()

    filtered = genome_allow is not None or sample_allow is not None
    return DenseMatrix(
        key_name=sources[0].key_name,
        genomes=tuple(ordered_genomes),
        samples=tuple(ordered_samples),
        values=values,
        sources=tuple(sources),
        non_zero_cells=loaded if not filtered else len(values),
        declared_cells=sum(source.declared_cells for source in sources),
        filtered=filtered,
    )


def _casefold_set(values: Sequence[str] | None) -> set[str] | None:
    if not values:
        return None
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _resolve_genome_filter(
    connection,
    sources: Sequence[MatrixSource],
    genomes: Sequence[str] | None,
    taxonomy: Mapping[str, str] | None,
) -> set[str] | None:
    """Resolve explicit genome IDs and taxonomy filters into an allowed set."""
    allowed: set[str] | None = None

    if genomes:
        wanted = _casefold_set(genomes) or set()
        allowed = {
            genome
            for source in sources
            for genome in source.genomes
            if genome.lower() in wanted
        }

    active_ranks = {
        rank: value
        for rank, value in (taxonomy or {}).items()
        if value is not None and str(value).strip()
    }
    if active_ranks:
        conditions = []
        parameters: list[Any] = []
        for rank, value in active_ranks.items():
            if rank not in TAXONOMY_PREFIXES:
                raise QueryValidationError(f"Unknown taxonomic rank: {rank}.")
            prefix = TAXONOMY_PREFIXES[rank]
            parts = [part.strip() for part in str(value).split(",") if part.strip()]
            stripped = [
                part[len(prefix):] if part.lower().startswith(prefix.lower()) else part
                for part in parts
            ]
            placeholders = ", ".join("LOWER(?)" for _ in stripped)
            conditions.append(
                f'LOWER(CASE WHEN "{rank}" LIKE \'{prefix}%\' '
                f'THEN substr("{rank}", {len(prefix) + 1}) ELSE "{rank}" END) '
                f"IN ({placeholders})"
            )
            parameters.extend(stripped)

        rows = connection.execute(
            f'SELECT DISTINCT "genome" FROM "genome_metadata" '
            f"WHERE {' AND '.join(conditions)}",
            parameters,
        ).fetchall()
        by_taxonomy = {row["genome"] for row in rows}
        allowed = by_taxonomy if allowed is None else allowed & by_taxonomy

    return allowed


def sample_coordinates(
    catalog_path: str | Path,
    samples: Sequence[str],
    *,
    level: str,
) -> list[dict[str, Any]]:
    """Return the spatial and contextual metadata for a matrix's columns.

    The companion table to a dense export: one row per matrix column, in matrix
    order, carrying the coordinates that make a spatial analysis possible.

    For ``micro`` the sample identifiers are sequencing library IDs, so the
    laser-capture coordinates are reached across the ENA-accession bridge; a
    library with no matching ``microsamples`` row yields nulls rather than
    being dropped.
    """
    if not samples:
        return []
    resolved = resolve_catalog_path(catalog_path)
    placeholders = ", ".join("?" for _ in samples)

    if level == "micro":
        sql = f"""
        SELECT
            q."microsample_id" AS "sample",
            mi."microsample_id" AS "microsample_id",
            q."cryosection_id",
            mi."sample_type",
            mi."size",
            mi."x_coord",
            mi."y_coord",
            q."pixel_x",
            q."pixel_y",
            q."shape",
            q."run_accession"
        FROM "microsample_sequencing" AS q
        LEFT JOIN "microsamples" AS mi
            ON mi."ena_accession" IS NOT NULL AND mi."ena_accession" <> ''
            AND mi."ena_accession" = q."run_accession"
        WHERE q."microsample_id" IN ({placeholders})
        """
    else:
        sql = f"""
        SELECT
            ms."library_id" AS "sample",
            ma."macrosample_id",
            ms."experimental_unit" AS "specimen_id",
            ma."sample_type",
            ma."data_type",
            ms."run_accession"
        FROM "macrosample_sequencing" AS ms
        LEFT JOIN "macrosamples" AS ma
            ON ma."ena_accession" IS NOT NULL AND ma."ena_accession" <> ''
            AND ma."ena_accession" = ms."run_accession"
        WHERE ms."library_id" IN ({placeholders})
        """

    connection = connect(resolved)
    try:
        rows = {row["sample"]: dict(row) for row in connection.execute(sql, list(samples))}
    finally:
        connection.close()

    headers = (
        MICRO_COORDINATE_HEADERS if level == "micro" else MACRO_COORDINATE_HEADERS
    )
    return [
        rows.get(sample) or {header: (sample if header == "sample" else None) for header in headers}
        for sample in samples
    ]


MICRO_COORDINATE_HEADERS = (
    "sample",
    "microsample_id",
    "cryosection_id",
    "sample_type",
    "size",
    "x_coord",
    "y_coord",
    "pixel_x",
    "pixel_y",
    "shape",
    "run_accession",
)

MACRO_COORDINATE_HEADERS = (
    "sample",
    "macrosample_id",
    "specimen_id",
    "sample_type",
    "data_type",
    "run_accession",
)
