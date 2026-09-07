"""Distinct-value counting."""

from __future__ import annotations

import pytest

from threedtk.query import QueryValidationError
from threedtk.values import value_rows


def test_counts_are_ordered_by_descending_count(catalog) -> None:
    field, rows = value_rows(catalog, target="microsamples", field="sample_type")
    assert field == "sample_type"
    assert [(r["value"], r["count"]) for r in rows] == [
        ("Positive", 3), ("NegativeMembrane", 1)
    ]


def test_blank_and_null_values_are_excluded(catalog) -> None:
    _, rows = value_rows(catalog, target="macrosamples", field="metabolights_accession")
    assert [r["value"] for r in rows] == ["MTBLS1"]


def test_filters_apply_before_counting(catalog) -> None:
    _, rows = value_rows(
        catalog, target="microsamples", field="sample_type",
        filters={"microsample_id": "CRYO1-003"},
    )
    assert [r["value"] for r in rows] == ["NegativeMembrane"]


def test_taxonomy_values_are_returned_without_prefixes(catalog) -> None:
    _, rows = value_rows(catalog, target="genomes", field="phylum")
    assert all(not r["value"].startswith("p__") for r in rows)
    assert "Bacillota_A" in {r["value"] for r in rows}


def test_derived_quality_can_be_counted(catalog) -> None:
    _, rows = value_rows(catalog, target="genomes", field="quality")
    assert {r["value"] for r in rows} == {"high", "medium", "low"}


def test_aliases_resolve_to_canonical_fields(catalog) -> None:
    field, _ = value_rows(catalog, target="specimens", field="species")
    assert field == "species_scientific"


def test_limit_caps_the_result(catalog) -> None:
    _, rows = value_rows(catalog, target="genomes", field="phylum", limit=1)
    assert len(rows) == 1


def test_unknown_field_is_rejected(catalog) -> None:
    with pytest.raises(QueryValidationError):
        value_rows(catalog, target="genomes", field="nope")


def test_non_positive_limit_is_rejected(catalog) -> None:
    with pytest.raises(QueryValidationError):
        value_rows(catalog, target="genomes", field="phylum", limit=0)


def test_fields_listing_marks_aliases() -> None:
    from threedtk.fields import value_field_rows

    rows = {row["field"]: row for row in value_field_rows("specimens")}
    assert rows["species"]["type"] == "alias"
    assert rows["species"]["resolves_to"] == "species_scientific"
    assert rows["sex"]["type"] == "field"
