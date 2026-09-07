"""Declarative query engine over the 3D'omics catalogue.

Every target -- ``experiments`` through ``counts`` -- is declared once in
:data:`TARGETS` as a :class:`TargetConfig`, and the CLI, the Python API,
``values``, ``fields`` and ``stats`` are all generated from that declaration.
Adding a column means editing one registry entry, not five call sites.

Filters are always parameterised. The escape hatch, ``--where``, is checked
against :data:`_BANNED_SQL_PATTERN` and rejected if it carries statement
terminators, comments, or mutating keywords; the catalogue is opened read-only
regardless.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from threedtk.catalog import resolve_catalog_path as _resolve_catalog_path
from threedtk.sources import (
    COUNTS_SOURCE,
    CRYOSECTIONS_SOURCE,
    EXPERIMENTS_SOURCE,
    GENOMES_SOURCE,
    MACROSAMPLES_SOURCE,
    MICROSAMPLES_SOURCE,
    SPECIMENS_SOURCE,
)

DEFAULT_QUERY_LIMIT = 50
CATALOG_META_TABLE = "catalog_meta"
CUSTOM_COLUMNS_RESOURCE = resources.files("threedtk").joinpath(
    "data", "custom_columns.json"
)

#: Catalogue ``schema_version`` values this ``3dtk`` release can read. Keep in
#: sync with ``database-build``'s ``SCHEMA_VERSION``. Catalogues that predate
#: the ``catalog_meta`` table are treated as legacy and accepted.
SUPPORTED_SCHEMA_VERSIONS = frozenset({2})

#: GTDB rank prefixes, stripped for display but kept filterable in raw form.
TAXONOMY_PREFIXES = {
    "domain": "d__",
    "phylum": "p__",
    "class": "c__",
    "order": "o__",
    "family": "f__",
    "genus": "g__",
    "species": "s__",
}

_BANNED_SQL_PATTERN = re.compile(
    r"\b(?:DROP|DELETE|INSERT|UPDATE|ALTER|ATTACH|DETACH|CREATE|REPLACE|VACUUM|PRAGMA)\b",
    flags=re.IGNORECASE,
)


class QueryValidationError(ValueError):
    """Raised when a user-provided target, column, field, or SQL fragment is invalid."""


class UnsupportedSchemaVersionError(RuntimeError):
    """Raised when a catalogue's ``schema_version`` is not supported by this 3dtk."""


@dataclass(frozen=True)
class TargetConfig:
    """Everything the engine needs to serve one target.

    Attributes:
        source: A table, view, or inline join SQL expression to select from.
        query_columns: Header name -> SELECT expression, for ``query``.
        all_query_headers: Every header, in display order (``--columns all``).
        fetch_select: Columns ``fetch`` needs to resolve downloads.
        fetch_headers: Header names matching ``fetch_select``.
        order_by: Deterministic ordering for query output.
        primary_id: The record identifier column.
        label: Human-readable plural name, for titles and messages.
    """

    source: str
    query_columns: Mapping[str, str]
    all_query_headers: tuple[str, ...]
    fetch_select: tuple[str, ...]
    fetch_headers: tuple[str, ...]
    order_by: str
    primary_id: str
    label: str


def _taxonomy_select(column: str, prefix: str, alias: str) -> str:
    """Strip a GTDB rank prefix for display, leaving unprefixed values alone."""
    prefix_length = len(prefix) + 1
    return (
        f'CASE WHEN "{column}" LIKE \'{prefix}%\' '
        f'THEN substr("{column}", {prefix_length}) ELSE "{column}" END AS "{alias}"'
    )


def _taxonomy_expr(column: str, prefix: str) -> str:
    prefix_length = len(prefix) + 1
    return (
        f'CASE WHEN "{column}" LIKE \'{prefix}%\' '
        f'THEN substr("{column}", {prefix_length}) ELSE "{column}" END'
    )


#: MIMAG-style quality tiers derived from completeness and contamination.
GENOME_QUALITY_CASE_EXPR = (
    "CASE "
    'WHEN "completeness" >= 90 AND "contamination" <= 5 THEN \'high\' '
    'WHEN "completeness" >= 50 AND "contamination" <= 10 THEN \'medium\' '
    "ELSE 'low' END"
)


def _plain(*names: str) -> dict[str, str]:
    return {name: f'"{name}"' for name in names}


_EXPERIMENT_COLUMNS = _plain(
    "experiment_id",
    "experiment_name",
    "experiment_type",
    "start_date",
    "end_date",
    "description",
    "bioproject_accession",
    "bioproject_link",
    "mag_description",
    "mag_completeness_avg",
    "mag_contamination_avg",
    "mag_new_species_pct",
    "mag_count",
    "doi",
    "link",
    "has_genome_catalogue",
)

_SPECIMEN_COLUMNS = _plain(
    "specimen_id",
    "experiment_id",
    "experiment_name",
    "experiment_type",
    "biosample_accession",
    "biosample_link",
    "pen",
    "slaughtering_date",
    "slaughtering_day_count",
    "treatment",
    "treatment_name",
    "treatment_group",
    "weight",
    "dpi",
    "sex",
    "species_scientific",
    "species_common",
    "taxid",
    "lifestage",
)

_MACROSAMPLE_COLUMNS = _plain(
    "macrosample_id",
    "code",
    "container",
    "data_type",
    "description",
    "preservative",
    "sample_type",
    "ena_accession",
    "ena_link",
    "metabolights_accession",
    "metabolights_link",
    "library_id",
    "run_accession",
    "experimental_unit",
    "specimen_id",
    "experiment_id",
    "experiment_name",
    "pen",
    "dpi",
    "treatment",
    "treatment_group",
    "specimen_weight",
    "sex",
    "species_scientific",
    "species_common",
    "taxid",
    "lifestage",
)

_CRYOSECTION_COLUMNS = _plain(
    "cryosection_id",
    "macrosample_id",
    "microsample_count",
    "position",
    "slide",
    "slide_date",
    "has_image",
    "sample_type",
    "data_type",
    "specimen_id",
    "experiment_id",
    "experiment_name",
    "treatment",
    "treatment_group",
    "sex",
    "species_scientific",
    "species_common",
    "taxid",
    "lifestage",
)

_MICROSAMPLE_COLUMNS = _plain(
    "microsample_id",
    "cryosection_id",
    "collection_method",
    "date",
    "lm_batch",
    "sample_type",
    "size",
    "x_coord",
    "y_coord",
    "ena_accession",
    "ena_link",
    "library_id",
    "run_accession",
    "shape",
    "pixel_x",
    "pixel_y",
    "macrosample_id",
    "cryosection_position",
    "slide",
    "slide_date",
    "specimen_id",
    "macrosample_type",
    "data_type",
    "experiment_id",
    "experiment_name",
    "pen",
    "dpi",
    "treatment",
    "treatment_group",
    "sex",
    "species_scientific",
    "species_common",
    "taxid",
    "lifestage",
)

_GENOME_COLUMNS = {
    **_plain(
        "genome",
        "experiment_id",
        "experiment_name",
        "source_id",
        "completeness",
        "contamination",
        "length",
    ),
    "quality": f'{GENOME_QUALITY_CASE_EXPR} AS "quality"',
    **{
        rank: _taxonomy_select(rank, prefix, rank)
        for rank, prefix in TAXONOMY_PREFIXES.items()
    },
}

_COUNTS_COLUMNS = {
    **_plain(
        "level",
        "experiment_id",
        "cryosection_id",
        "source_id",
        "genome",
        "sample",
        "count",
        "specimen_id",
        "macrosample_id",
        "sample_type",
        "x_coord",
        "y_coord",
        "pixel_x",
        "pixel_y",
        "completeness",
        "contamination",
    ),
    **{
        rank: _taxonomy_select(rank, prefix, rank)
        for rank, prefix in TAXONOMY_PREFIXES.items()
    },
}


def _headers(columns: Mapping[str, str], order: tuple[str, ...]) -> tuple[str, ...]:
    missing = [name for name in order if name not in columns]
    if missing:  # pragma: no cover - guards registry edits
        raise QueryValidationError(f"Unknown headers declared: {', '.join(missing)}.")
    return order


_GENOME_HEADER_ORDER = (
    "genome",
    "experiment_id",
    "experiment_name",
    "source_id",
    "quality",
    "completeness",
    "contamination",
    "length",
    "domain",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)

_COUNTS_HEADER_ORDER = (
    "level",
    "experiment_id",
    "cryosection_id",
    "source_id",
    "genome",
    "sample",
    "count",
    "specimen_id",
    "macrosample_id",
    "sample_type",
    "x_coord",
    "y_coord",
    "pixel_x",
    "pixel_y",
    "domain",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
    "completeness",
    "contamination",
)


TARGETS: dict[str, TargetConfig] = {
    "experiments": TargetConfig(
        source=EXPERIMENTS_SOURCE,
        query_columns=_EXPERIMENT_COLUMNS,
        all_query_headers=tuple(_EXPERIMENT_COLUMNS),
        fetch_select=(),
        fetch_headers=(),
        order_by='"experiment_id"',
        primary_id="experiment_id",
        label="experiments",
    ),
    "specimens": TargetConfig(
        source=SPECIMENS_SOURCE,
        query_columns=_SPECIMEN_COLUMNS,
        all_query_headers=tuple(_SPECIMEN_COLUMNS),
        fetch_select=(),
        fetch_headers=(),
        order_by='"specimen_id"',
        primary_id="specimen_id",
        label="specimens",
    ),
    "macrosamples": TargetConfig(
        source=MACROSAMPLES_SOURCE,
        query_columns=_MACROSAMPLE_COLUMNS,
        all_query_headers=tuple(_MACROSAMPLE_COLUMNS),
        fetch_select=(
            '"macrosample_id"',
            '"specimen_id"',
            '"experiment_id"',
            '"data_type"',
            '"sample_type"',
            '"ena_accession"',
            '"run_accession"',
            '"metabolights_accession"',
            '"metabolights_link"',
        ),
        fetch_headers=(
            "macrosample_id",
            "specimen_id",
            "experiment_id",
            "data_type",
            "sample_type",
            "ena_accession",
            "run_accession",
            "metabolights_accession",
            "metabolights_link",
        ),
        order_by='"macrosample_id"',
        primary_id="macrosample_id",
        label="macrosamples",
    ),
    "cryosections": TargetConfig(
        source=CRYOSECTIONS_SOURCE,
        query_columns=_CRYOSECTION_COLUMNS,
        all_query_headers=tuple(_CRYOSECTION_COLUMNS),
        fetch_select=(),
        fetch_headers=(),
        order_by='"cryosection_id"',
        primary_id="cryosection_id",
        label="cryosections",
    ),
    "microsamples": TargetConfig(
        source=MICROSAMPLES_SOURCE,
        query_columns=_MICROSAMPLE_COLUMNS,
        all_query_headers=tuple(_MICROSAMPLE_COLUMNS),
        fetch_select=(
            '"microsample_id"',
            '"library_id"',
            '"cryosection_id"',
            '"specimen_id"',
            '"experiment_id"',
            '"ena_accession"',
            '"run_accession"',
            '"sample_type"',
            '"x_coord"',
            '"y_coord"',
        ),
        fetch_headers=(
            "microsample_id",
            "library_id",
            "cryosection_id",
            "specimen_id",
            "experiment_id",
            "ena_accession",
            "run_accession",
            "sample_type",
            "x_coord",
            "y_coord",
        ),
        order_by='"microsample_id"',
        primary_id="microsample_id",
        label="microsamples",
    ),
    "genomes": TargetConfig(
        source=GENOMES_SOURCE,
        query_columns=_GENOME_COLUMNS,
        all_query_headers=_headers(_GENOME_COLUMNS, _GENOME_HEADER_ORDER),
        fetch_select=(),
        fetch_headers=(),
        order_by='"experiment_id", "genome"',
        primary_id="genome",
        label="genomes",
    ),
    "counts": TargetConfig(
        source=COUNTS_SOURCE,
        query_columns=_COUNTS_COLUMNS,
        all_query_headers=_headers(_COUNTS_COLUMNS, _COUNTS_HEADER_ORDER),
        fetch_select=(),
        fetch_headers=(),
        order_by='"level", "genome", "sample"',
        primary_id="genome",
        label="counts",
    ),
}

#: Friendly aliases accepted by ``--field`` and ``--columns``.
FIELD_ALIASES: dict[str, dict[str, str]] = {
    "experiments": {"name": "experiment_name", "type": "experiment_type"},
    "specimens": {
        "species": "species_scientific",
        "common_name": "species_common",
        "experiment": "experiment_id",
    },
    "macrosamples": {
        "species": "species_scientific",
        "experiment": "experiment_id",
        "specimen": "specimen_id",
    },
    "cryosections": {
        "species": "species_scientific",
        "experiment": "experiment_id",
        "macrosample": "macrosample_id",
    },
    "microsamples": {
        "species": "species_scientific",
        "experiment": "experiment_id",
        "cryosection": "cryosection_id",
        "x": "x_coord",
        "y": "y_coord",
    },
    "genomes": {"experiment": "experiment_id"},
    "counts": {"experiment": "experiment_id", "cryosection": "cryosection_id"},
}


def resolve_catalog_path(catalog_path: str | Path | None = None) -> Path:
    """Resolve a catalogue path, downloading the pinned release if needed."""
    return _resolve_catalog_path(catalog_path)


def catalog_path_from_context(ctx: Any, catalog_path: str | Path | None = None) -> Path:
    """Resolve the catalogue for a Typer command, preferring the root context."""
    if catalog_path is not None:
        return resolve_catalog_path(catalog_path)
    if getattr(ctx, "obj", None) and "catalog_path" in ctx.obj:
        return Path(ctx.obj["catalog_path"])
    return resolve_catalog_path(None)


def connect(catalog_path: str | Path) -> sqlite3.Connection:
    """Open a catalogue read-only with row access by name."""
    path = Path(catalog_path)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


@lru_cache(maxsize=1)
def _custom_query_headers() -> dict[str, dict[str, tuple[str, ...]]]:
    with CUSTOM_COLUMNS_RESOURCE.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return {
        target: {preset: tuple(columns) for preset, columns in presets.items()}
        for target, presets in raw.items()
    }


@lru_cache(maxsize=None)
def read_catalog_meta(catalog_path: Path) -> dict[str, str]:
    """Return the ``catalog_meta`` key/value map, or ``{}`` for legacy catalogues."""
    try:
        connection = connect(catalog_path)
    except sqlite3.Error:
        return {}
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (CATALOG_META_TABLE,),
        ).fetchone()
        if exists is None:
            return {}
        rows = connection.execute(
            f'SELECT key, value FROM "{CATALOG_META_TABLE}"'
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        connection.close()
    return {str(row["key"]): str(row["value"]) for row in rows}


def validate_catalog_schema(catalog_path: Path) -> None:
    """Raise if the catalogue's ``schema_version`` is unsupported.

    Catalogues without a ``catalog_meta`` table, or without a recorded
    ``schema_version``, are treated as legacy and accepted. A present but
    out-of-range version raises :class:`UnsupportedSchemaVersionError`.
    """
    raw_version = read_catalog_meta(catalog_path).get("schema_version")
    if raw_version is None:
        return
    try:
        schema_version = int(raw_version)
    except (TypeError, ValueError):
        raise UnsupportedSchemaVersionError(
            f"Catalogue at {catalog_path} has an unreadable schema_version "
            f"({raw_version!r})."
        ) from None
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_SCHEMA_VERSIONS))
        raise UnsupportedSchemaVersionError(
            f"Catalogue schema_version {schema_version} is not supported by this "
            f"3dtk (supported: {supported}). Install a 3dtk version that matches "
            "the catalogue, or use a catalogue built for this 3dtk."
        )


def headers_for(
    target: str,
    *,
    fetch: bool = False,
    columns: str | None = None,
) -> tuple[str, ...]:
    """Return the output headers for a query or fetch."""
    if fetch:
        return TARGETS[target].fetch_headers
    return resolve_query_headers(target, columns)


def resolve_query_headers(target: str, columns: str | None = None) -> tuple[str, ...]:
    """Resolve ``--columns`` into a header tuple: a preset, ``all``, or a list."""
    if target not in TARGETS:
        raise QueryValidationError(f"Unsupported query target: {target}.")
    config = TARGETS[target]
    presets = _custom_query_headers().get(target)
    if presets is None:
        raise QueryValidationError(f"No custom columns configured for target: {target}.")

    if columns is None:
        return presets["default"]

    keyword = columns.strip().lower()
    if not keyword:
        raise QueryValidationError("The --columns option must not be empty.")
    if keyword == "all":
        return config.all_query_headers

    if "," not in columns:
        if keyword in presets:
            return presets[keyword]
        known = {name for target_presets in _custom_query_headers().values() for name in target_presets}
        if keyword in known:
            available = ", ".join(sorted(presets))
            raise QueryValidationError(
                f"Column preset '{keyword}' is not available for {target}. "
                f"Available presets: {available}."
            )

    aliases = FIELD_ALIASES.get(target, {})
    requested = tuple(
        aliases.get(column.strip(), column.strip())
        for column in columns.split(",")
        if column.strip()
    )
    invalid = [column for column in requested if column not in config.query_columns]
    if invalid:
        raise QueryValidationError(
            f"Unknown columns for {target}: {', '.join(invalid)}. "
            f"Available columns: {', '.join(config.all_query_headers)}."
        )
    return requested


def select_expressions_for(target: str, headers: tuple[str, ...]) -> tuple[str, ...]:
    config = TARGETS[target]
    return tuple(config.query_columns[header] for header in headers)


def available_value_fields(target: str) -> tuple[str, ...]:
    if target not in TARGETS:
        raise QueryValidationError(f"Unsupported query target: {target}.")
    fields = list(TARGETS[target].all_query_headers)
    for alias in FIELD_ALIASES.get(target, {}):
        if alias not in fields:
            fields.append(alias)
    return tuple(fields)


def resolve_value_field(target: str, field: str) -> str:
    if target not in TARGETS:
        raise QueryValidationError(f"Unsupported query target: {target}.")
    candidate = field.strip()
    if not candidate:
        raise QueryValidationError("The --field option must not be empty.")
    canonical = FIELD_ALIASES.get(target, {}).get(candidate, candidate)
    if canonical in TARGETS[target].all_query_headers:
        return canonical
    raise QueryValidationError(
        f"Unknown values field for {target}: {field}. "
        f"Available fields: {', '.join(available_value_fields(target))}."
    )


def value_expression_for(target: str, field: str) -> str:
    """Return the SQL expression whose distinct values ``values`` counts."""
    canonical = resolve_value_field(target, field)
    if canonical == "quality" and target == "genomes":
        return GENOME_QUALITY_CASE_EXPR
    if canonical in TAXONOMY_PREFIXES and target in {"genomes", "counts"}:
        return _taxonomy_expr(canonical, TAXONOMY_PREFIXES[canonical])
    return f'"{canonical}"'


def primary_id_for(target: str) -> str:
    if target not in TARGETS:
        raise QueryValidationError(f"Unsupported query target: {target}.")
    return TARGETS[target].primary_id


def validate_where_clause(where: str | None) -> str | None:
    """Validate a raw ``--where`` fragment, or return ``None`` when empty."""
    if where is None:
        return None
    candidate = where.strip()
    if not candidate:
        return None
    if ";" in candidate:
        raise QueryValidationError("The --where clause must not contain semicolons.")
    if "--" in candidate or "/*" in candidate or "*/" in candidate:
        raise QueryValidationError("The --where clause must not contain SQL comments.")
    if _BANNED_SQL_PATTERN.search(candidate):
        raise QueryValidationError("The --where clause contains a banned SQL keyword.")
    return candidate


def _split_filter_values(value: Any | None) -> list[str]:
    """Split a comma-separated filter value into trimmed, non-empty parts."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _casefold_one_of(expression: str, value_count: int) -> str:
    placeholders = ", ".join("LOWER(?)" for _ in range(value_count))
    return f"LOWER(COALESCE({expression}, '')) IN ({placeholders})"


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.lower().startswith(prefix.lower()) else value


def _build_conditions(
    target: str,
    filters: Mapping[str, Any],
) -> tuple[list[str], list[Any]]:
    """Translate a filter mapping into parameterised SQL conditions."""
    conditions: list[str] = []
    parameters: list[Any] = []

    def add_exact(column: str, key: str) -> None:
        values = _split_filter_values(filters.get(key))
        if values:
            conditions.append(_casefold_one_of(f'"{column}"', len(values)))
            parameters.extend(values)

    def add_any_of(columns: tuple[str, ...], key: str) -> None:
        """Match a value against any one of several columns (e.g. species names)."""
        values = _split_filter_values(filters.get(key))
        if not values:
            return
        conditions.append(
            "("
            + " OR ".join(_casefold_one_of(f'"{c}"', len(values)) for c in columns)
            + ")"
        )
        for _ in columns:
            parameters.extend(values)

    def add_taxonomy(rank: str, key: str | None = None) -> None:
        """Match a GTDB rank with or without its ``x__`` prefix."""
        values = _split_filter_values(filters.get(key or rank))
        if not values:
            return
        prefix = TAXONOMY_PREFIXES[rank]
        conditions.append(
            _casefold_one_of(_taxonomy_expr(rank, prefix), len(values))
        )
        parameters.extend(_strip_prefix(value, prefix) for value in values)

    def add_range(column: str, min_key: str, max_key: str) -> None:
        minimum = filters.get(min_key)
        maximum = filters.get(max_key)
        if minimum is not None:
            conditions.append(f'"{column}" >= ?')
            parameters.append(minimum)
        if maximum is not None:
            conditions.append(f'"{column}" <= ?')
            parameters.append(maximum)

    def add_flag(column: str, key: str) -> None:
        """Filter on a 0/1 catalogue flag when the option was given."""
        value = filters.get(key)
        if value is None:
            return
        conditions.append(f'COALESCE("{column}", 0) = ?')
        parameters.append(1 if value else 0)

    def add_presence(column: str, key: str) -> None:
        """Filter on whether a text column carries a value at all."""
        value = filters.get(key)
        if value is None:
            return
        if value:
            conditions.append(f'("{column}" IS NOT NULL AND "{column}" <> \'\')')
        else:
            conditions.append(f'("{column}" IS NULL OR "{column}" = \'\')')

    def add_specimen_context() -> None:
        add_exact("specimen_id", "specimen_id")
        add_exact("experiment_id", "experiment_id")
        add_exact("sex", "sex")
        add_exact("treatment", "treatment")
        add_exact("treatment_group", "treatment_group")
        add_exact("lifestage", "lifestage")
        add_exact("taxid", "taxid")
        add_any_of(("species_scientific", "species_common"), "species")

    def add_bounding_box() -> None:
        add_range("x_coord", "x_min", "x_max")
        add_range("y_coord", "y_min", "y_max")

    if target == "experiments":
        add_exact("experiment_id", "experiment_id")
        add_exact("experiment_type", "experiment_type")
        add_flag("has_genome_catalogue", "has_genome_catalogue")

    elif target == "specimens":
        add_specimen_context()
        add_exact("pen", "pen")
        add_range("weight", "weight_min", "weight_max")
        add_range("dpi", "dpi_min", "dpi_max")

    elif target == "macrosamples":
        add_exact("macrosample_id", "macrosample_id")
        add_specimen_context()
        add_exact("data_type", "data_type")
        add_exact("sample_type", "sample_type")
        add_exact("preservative", "preservative")
        add_exact("container", "container")
        add_exact("code", "code")
        add_exact("library_id", "library_id")
        add_exact("ena_accession", "ena_accession")
        add_exact("metabolights_accession", "metabolights_accession")
        add_presence("ena_accession", "has_ena")
        add_presence("metabolights_accession", "has_metabolights")

    elif target == "cryosections":
        add_exact("cryosection_id", "cryosection_id")
        add_exact("macrosample_id", "macrosample_id")
        add_specimen_context()
        add_exact("position", "position")
        add_exact("slide", "slide")
        add_exact("sample_type", "sample_type")
        add_flag("has_image", "has_image")

    elif target == "microsamples":
        add_exact("microsample_id", "microsample_id")
        add_exact("library_id", "library_id")
        add_exact("cryosection_id", "cryosection_id")
        add_exact("macrosample_id", "macrosample_id")
        add_specimen_context()
        add_exact("sample_type", "sample_type")
        add_exact("collection_method", "collection_method")
        add_exact("lm_batch", "lm_batch")
        add_exact("shape", "shape")
        add_exact("ena_accession", "ena_accession")
        add_range("size", "size_min", "size_max")
        add_bounding_box()
        add_range("pixel_x", "pixel_x_min", "pixel_x_max")
        add_range("pixel_y", "pixel_y_min", "pixel_y_max")
        add_presence("run_accession", "has_sequencing")

    elif target == "genomes":
        add_exact("genome", "genome")
        add_exact("experiment_id", "experiment_id")
        for rank in TAXONOMY_PREFIXES:
            add_taxonomy(rank)
        add_range("completeness", "completeness_min", "completeness_max")
        add_range("contamination", "contamination_min", "contamination_max")
        add_range("length", "length_min", "length_max")
        quality_values = _split_filter_values(filters.get("quality"))
        if quality_values:
            conditions.append(
                "(" + " OR ".join(_quality_clause(v) for v in quality_values) + ")"
            )

    elif target == "counts":
        add_exact("level", "level")
        add_exact("experiment_id", "experiment_id")
        add_exact("cryosection_id", "cryosection_id")
        add_exact("genome", "genome")
        add_exact("sample", "sample")
        add_exact("specimen_id", "specimen_id")
        add_exact("macrosample_id", "macrosample_id")
        add_exact("sample_type", "sample_type")
        for rank in TAXONOMY_PREFIXES:
            add_taxonomy(rank)
        add_range("count", "count_min", "count_max")
        add_bounding_box()

    else:
        raise QueryValidationError(f"Unsupported query target: {target}.")

    return conditions, parameters


def _quality_clause(quality: str) -> str:
    name = quality.strip().lower()
    if name == "high":
        return '("completeness" >= 90 AND "contamination" <= 5)'
    if name == "medium":
        return '("completeness" >= 50 AND "contamination" <= 10 AND NOT ("completeness" >= 90 AND "contamination" <= 5))'
    if name == "low":
        return 'NOT ("completeness" >= 50 AND "contamination" <= 10)'
    raise QueryValidationError(
        f"Unsupported genome quality value: {quality}. Use high, medium, or low."
    )


def build_filtered_source_query(
    target: str,
    *,
    filters: Mapping[str, Any] | None = None,
    where: str | None = None,
) -> tuple[str, list[Any]]:
    """Build the filtered sub-select every action shares."""
    if target not in TARGETS:
        raise QueryValidationError(f"Unsupported query target: {target}.")
    conditions, parameters = _build_conditions(target, filters or {})
    safe_where = validate_where_clause(where)
    if safe_where:
        conditions.append(f"({safe_where})")

    sql = f"SELECT * FROM {TARGETS[target].source}"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    return sql, parameters


def build_query(
    target: str,
    *,
    filters: Mapping[str, Any] | None = None,
    where: str | None = None,
    limit: int | None = None,
    fetch: bool = False,
    columns: str | None = None,
) -> tuple[str, list[Any]]:
    """Build a complete ``query`` (or ``fetch``) statement and its parameters."""
    if target not in TARGETS:
        raise QueryValidationError(f"Unsupported query target: {target}.")
    config = TARGETS[target]
    if fetch and not config.fetch_select:
        raise QueryValidationError(f"Target {target} has no downloadable files.")

    selected = (
        config.fetch_select
        if fetch
        else select_expressions_for(target, resolve_query_headers(target, columns))
    )
    base_sql, parameters = build_filtered_source_query(
        target, filters=filters, where=where
    )
    sql = f"SELECT {', '.join(selected)} FROM ({base_sql}) AS filtered"
    sql += f" ORDER BY {config.order_by}"

    if limit is not None:
        if limit <= 0:
            raise QueryValidationError("The query limit must be greater than zero.")
        sql += " LIMIT ?"
        parameters.append(limit)
    return sql, parameters


def query_rows(
    catalog_path: str | Path | None,
    target: str,
    *,
    filters: Mapping[str, Any] | None = None,
    where: str | None = None,
    limit: int | None = None,
    fetch: bool = False,
    columns: str | None = None,
) -> list[sqlite3.Row]:
    """Run a query against a catalogue and return its rows."""
    resolved = resolve_catalog_path(catalog_path)
    sql, parameters = build_query(
        target,
        filters=filters,
        where=where,
        limit=limit,
        fetch=fetch,
        columns=columns,
    )
    connection = connect(resolved)
    try:
        return connection.execute(sql, parameters).fetchall()
    finally:
        connection.close()


def count_rows(
    catalog_path: str | Path | None,
    target: str,
    *,
    filters: Mapping[str, Any] | None = None,
    where: str | None = None,
) -> int:
    """Count records matching the filters, ignoring any limit."""
    resolved = resolve_catalog_path(catalog_path)
    base_sql, parameters = build_filtered_source_query(
        target, filters=filters, where=where
    )
    connection = connect(resolved)
    try:
        row = connection.execute(
            f"SELECT COUNT(*) AS n FROM ({base_sql}) AS filtered", parameters
        ).fetchone()
        return int(row["n"])
    finally:
        connection.close()
