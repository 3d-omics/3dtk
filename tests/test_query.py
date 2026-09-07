"""Query engine: targets, columns, filters, and --where validation."""

from __future__ import annotations

import pytest

from threedtk.query import (
    TARGETS,
    QueryValidationError,
    UnsupportedSchemaVersionError,
    build_query,
    count_rows,
    headers_for,
    query_rows,
    read_catalog_meta,
    resolve_query_headers,
    validate_catalog_schema,
    validate_where_clause,
)

from conftest import build_catalog


@pytest.mark.parametrize("target", sorted(TARGETS))
def test_every_target_queries_with_default_columns(catalog, target) -> None:
    rows = query_rows(catalog, target, limit=1)
    assert rows, f"{target} returned no rows"
    assert set(headers_for(target)) <= set(rows[0].keys())


@pytest.mark.parametrize("target", sorted(TARGETS))
def test_every_target_supports_columns_all(catalog, target) -> None:
    rows = query_rows(catalog, target, limit=1, columns="all")
    assert tuple(rows[0].keys()) == TARGETS[target].all_query_headers


def test_denormalised_join_carries_parent_metadata(catalog) -> None:
    row = query_rows(
        catalog, "microsamples", filters={"microsample_id": "CRYO1-001"}, columns="all"
    )[0]
    assert row["cryosection_id"] == "CRYO1"
    assert row["macrosample_id"] == "X01aF"
    assert row["specimen_id"] == "X01"
    assert row["experiment_id"] == "X"
    assert row["species_scientific"] == "Gallus gallus"


def test_microsamples_join_sequencing_across_the_accession_bridge(catalog) -> None:
    """The two tables share no microsample_id values; they meet on the accession."""
    row = query_rows(
        catalog, "microsamples", filters={"microsample_id": "CRYO1-001"}, columns="all"
    )[0]
    assert row["library_id"] == "M001"
    assert row["run_accession"] == "ERR1"
    assert (row["x_coord"], row["y_coord"]) == (10.0, 20.0)
    assert (row["pixel_x"], row["pixel_y"]) == (1, 2)


def test_left_joins_keep_records_whose_parent_is_missing(catalog) -> None:
    """A microsample pointing at an absent cryosection must not vanish."""
    rows = query_rows(catalog, "microsamples", filters={"microsample_id": "ORPHAN-001"})
    assert len(rows) == 1
    assert query_rows(catalog, "microsamples", limit=None) and count_rows(
        catalog, "microsamples"
    ) == 4


def test_filters_are_case_insensitive_and_comma_separated(catalog) -> None:
    assert count_rows(catalog, "specimens", filters={"sex": "FEMALE"}) == 1
    assert count_rows(catalog, "specimens", filters={"sex": "female,male"}) == 2


def test_species_filter_matches_scientific_or_common_name(catalog) -> None:
    assert count_rows(catalog, "specimens", filters={"species": "Gallus gallus"}) == 2
    assert count_rows(catalog, "specimens", filters={"species": "chicken"}) == 2


def test_taxonomy_filters_accept_prefixed_and_bare_values(catalog) -> None:
    bare = count_rows(catalog, "genomes", filters={"genus": "Faeciplasma"})
    prefixed = count_rows(catalog, "genomes", filters={"genus": "g__Faeciplasma"})
    assert bare == prefixed == 1


def test_taxonomy_is_displayed_without_gtdb_prefixes(catalog) -> None:
    row = query_rows(catalog, "genomes", filters={"genome": "X:bin_1"}, columns="taxonomy")[0]
    assert row["domain"] == "Bacteria"
    assert row["species"] == "Faeciplasma gallinarum"


def test_genome_quality_tiers_partition_the_catalogue(catalog) -> None:
    tiers = {
        tier: count_rows(catalog, "genomes", filters={"quality": tier})
        for tier in ("high", "medium", "low")
    }
    assert tiers == {"high": 1, "medium": 1, "low": 1}
    assert sum(tiers.values()) == count_rows(catalog, "genomes")


def test_quality_filter_agrees_with_the_displayed_quality(catalog) -> None:
    for tier in ("high", "medium", "low"):
        rows = query_rows(
            catalog, "genomes", filters={"quality": tier}, columns="quality", limit=None
        )
        assert {row["quality"] for row in rows} == {tier}


def test_unknown_quality_value_is_rejected(catalog) -> None:
    with pytest.raises(QueryValidationError):
        count_rows(catalog, "genomes", filters={"quality": "excellent"})


def test_bounding_box_filters_microsamples(catalog) -> None:
    assert count_rows(
        catalog, "microsamples", filters={"x_min": 20.0, "x_max": 40.0}
    ) == 1


def test_numeric_range_filters(catalog) -> None:
    assert count_rows(catalog, "specimens", filters={"weight_min": 2.0}) == 1
    assert count_rows(catalog, "specimens", filters={"weight_max": 2.0}) == 1


def test_presence_filters(catalog) -> None:
    assert count_rows(catalog, "macrosamples", filters={"has_ena": True}) == 1
    assert count_rows(catalog, "macrosamples", filters={"has_metabolights": True}) == 1
    assert count_rows(catalog, "microsamples", filters={"has_sequencing": True}) == 3


def test_flag_filters(catalog) -> None:
    assert count_rows(catalog, "experiments", filters={"has_genome_catalogue": True}) == 1
    assert count_rows(catalog, "experiments", filters={"has_genome_catalogue": False}) == 1


def test_counts_level_discriminates_the_two_tables(catalog) -> None:
    assert count_rows(catalog, "counts", filters={"level": "micro"}) == 3
    assert count_rows(catalog, "counts", filters={"level": "macro"}) == 1


def test_counts_carry_taxonomy_and_coordinates(catalog) -> None:
    row = query_rows(
        catalog, "counts", filters={"level": "micro", "sample": "M001"}, columns="all"
    )[0]
    assert row["genus"] == "Faeciplasma"
    assert (row["x_coord"], row["y_coord"]) == (10.0, 20.0)
    assert (row["pixel_x"], row["pixel_y"]) == (1, 2)


@pytest.mark.parametrize(
    "clause",
    [
        "completeness > 90; DROP TABLE genomes",
        "1=1 -- comment",
        "1=1 /* comment */",
        "completeness > 90 OR (DELETE FROM genomes)",
        "PRAGMA table_info(genomes)",
    ],
)
def test_where_clause_rejects_unsafe_sql(clause) -> None:
    with pytest.raises(QueryValidationError):
        validate_where_clause(clause)


def test_where_clause_accepts_a_plain_predicate(catalog) -> None:
    assert validate_where_clause("completeness > 90") == "completeness > 90"
    assert count_rows(catalog, "genomes", where="completeness > 90") == 1


def test_unknown_target_is_rejected() -> None:
    with pytest.raises(QueryValidationError):
        build_query("hologenomes")


def test_unknown_column_is_rejected() -> None:
    with pytest.raises(QueryValidationError) as excinfo:
        resolve_query_headers("genomes", "not_a_column")
    assert "not_a_column" in str(excinfo.value)


def test_column_preset_from_another_target_is_reported_clearly() -> None:
    with pytest.raises(QueryValidationError) as excinfo:
        resolve_query_headers("experiments", "spatial")
    assert "not available for experiments" in str(excinfo.value)


def test_limit_must_be_positive() -> None:
    with pytest.raises(QueryValidationError):
        build_query("genomes", limit=0)


def test_fetch_is_rejected_for_targets_without_files() -> None:
    with pytest.raises(QueryValidationError):
        build_query("experiments", fetch=True)


def test_catalog_meta_and_schema_validation(catalog) -> None:
    meta = read_catalog_meta(catalog)
    assert meta["schema_version"] == "2"
    assert meta["data_version"] == "2026.01.01"
    validate_catalog_schema(catalog)


def test_unsupported_schema_version_raises(tmp_path) -> None:
    path = build_catalog(tmp_path / "future.sqlite", schema_version="99")
    with pytest.raises(UnsupportedSchemaVersionError) as excinfo:
        validate_catalog_schema(path)
    assert "99" in str(excinfo.value)


def test_catalog_without_schema_version_is_treated_as_legacy(tmp_path) -> None:
    path = build_catalog(tmp_path / "legacy.sqlite", schema_version=None)
    validate_catalog_schema(path)


def test_unreadable_schema_version_raises(tmp_path) -> None:
    path = build_catalog(tmp_path / "bad.sqlite", schema_version="not-a-number")
    with pytest.raises(UnsupportedSchemaVersionError):
        validate_catalog_schema(path)


def test_catalog_is_opened_read_only(catalog) -> None:
    import sqlite3

    from threedtk.query import connect

    connection = connect(catalog)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DROP TABLE specimens")
    finally:
        connection.close()
