"""Distinct-value counts for one field, after filters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from threedtk.query import (
    QueryValidationError,
    build_filtered_source_query,
    connect,
    resolve_catalog_path,
    resolve_value_field,
    value_expression_for,
)

DEFAULT_VALUES_LIMIT = 20


def value_rows(
    catalog_path: str | Path,
    *,
    target: str,
    field: str,
    filters: Mapping[str, Any] | None = None,
    where: str | None = None,
    limit: int = DEFAULT_VALUES_LIMIT,
) -> tuple[str, list[dict[str, str | int]]]:
    """Count distinct values of ``field`` among records matching the filters.

    Returns:
        The canonical field name (aliases resolved) and the value/count rows,
        ordered by descending count. Blank and null values are excluded.
    """
    if limit <= 0:
        raise QueryValidationError("The values limit must be greater than zero.")

    resolved = resolve_catalog_path(catalog_path)
    canonical_field = resolve_value_field(target, field)
    expression = value_expression_for(target, field)
    base_sql, parameters = build_filtered_source_query(
        target, filters=filters, where=where
    )

    sql = f"""
    SELECT CAST(value AS TEXT) AS value, COUNT(*) AS count
    FROM (SELECT {expression} AS value FROM ({base_sql}) AS filtered) AS distinct_values
    WHERE COALESCE(TRIM(CAST(value AS TEXT)), '') <> ''
    GROUP BY value
    ORDER BY count DESC, value ASC
    LIMIT ?
    """

    connection = connect(resolved)
    try:
        rows = connection.execute(sql, [*parameters, limit]).fetchall()
    finally:
        connection.close()

    return canonical_field, [
        {"value": row["value"], "count": row["count"]} for row in rows
    ]
