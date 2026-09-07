"""Dense matrix reconstruction: axis order, restored zeros, and round-trip."""

from __future__ import annotations

import pytest

from threedtk.counts import (
    CountsError,
    dense_matrix,
    list_matrix_sources,
    sample_coordinates,
)

from conftest import (
    MACRO_SAMPLES,
    MICRO_CELLS,
    MICRO_GENOMES,
    MICRO_SAMPLES,
    MICRO_SOURCE,
)


def _micro(catalog):
    return list_matrix_sources(catalog, level="micro")


def test_lists_both_levels(catalog) -> None:
    assert {s.level for s in list_matrix_sources(catalog)} == {"macro", "micro"}
    assert len(_micro(catalog)) == 1


def test_selectors_narrow_the_matrix_list(catalog) -> None:
    assert len(list_matrix_sources(catalog, cryosection_id="CRYO1")) == 1
    assert len(list_matrix_sources(catalog, source_id=MICRO_SOURCE)) == 1
    assert list_matrix_sources(catalog, cryosection_id="nope") == []


def test_micro_matrices_resolve_their_experiment_through_the_hierarchy(catalog) -> None:
    """microsample_counts has no experiment_id; it is derived via cryosections."""
    sources = list_matrix_sources(catalog, level="micro", experiment_id="X")
    assert [s.owner_value for s in sources] == ["CRYO1"]
    assert list_matrix_sources(catalog, level="micro", experiment_id="Y") == []


def test_axes_come_from_matrix_axes_not_from_the_sparse_rows(catalog) -> None:
    """X:bin_2 has no non-zero cell, so only matrix_axes knows it belongs."""
    matrix = dense_matrix(catalog, _micro(catalog))
    assert matrix.genomes == tuple(MICRO_GENOMES)
    assert matrix.samples == tuple(MICRO_SAMPLES)
    assert "X:bin_2" not in {genome for genome, _, _ in MICRO_CELLS}
    assert "X:bin_2" in matrix.genomes


def test_dense_rows_restore_dropped_zeros(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog))
    rows = {row["genome"]: row for row in matrix.rows()}
    assert rows["X:bin_1"] == {"genome": "X:bin_1", "M001": 10.5, "M002": 0, "M003": 3.25}
    assert rows["X:bin_2"] == {"genome": "X:bin_2", "M001": 0, "M002": 0, "M003": 0}
    assert len(rows) * len(matrix.samples) == 9


def test_headers_start_with_the_recorded_key_name(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog))
    assert matrix.headers() == ("genome", "M001", "M002", "M003")


def test_round_trip_matches_source_files_row_count(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog))
    assert matrix.non_zero_cells == matrix.declared_cells == len(MICRO_CELLS)
    matrix.verify()


def test_verify_detects_a_disagreement_with_provenance(catalog, monkeypatch) -> None:
    matrix = dense_matrix(catalog, _micro(catalog))
    broken = type(matrix)(
        key_name=matrix.key_name,
        genomes=matrix.genomes,
        samples=matrix.samples,
        values=matrix.values,
        sources=matrix.sources,
        non_zero_cells=matrix.non_zero_cells + 1,
        declared_cells=matrix.declared_cells,
    )
    with pytest.raises(CountsError):
        broken.verify()


def test_long_rows_skip_zeros_unless_asked(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog))
    assert len(list(matrix.long_rows())) == len(MICRO_CELLS)
    assert len(list(matrix.long_rows(include_zeros=True))) == 9


def test_taxonomy_filter_restricts_rows_and_keeps_column_order(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog), taxonomy={"genus": "Faeciplasma"})
    assert matrix.genomes == ("X:bin_1",)
    assert matrix.samples == tuple(MICRO_SAMPLES)


def test_taxonomy_filter_accepts_a_prefixed_value(catalog) -> None:
    bare = dense_matrix(catalog, _micro(catalog), taxonomy={"genus": "Faeciplasma"})
    prefixed = dense_matrix(catalog, _micro(catalog), taxonomy={"genus": "g__Faeciplasma"})
    assert bare.genomes == prefixed.genomes


def test_sample_filter_preserves_matrix_order(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog), samples=["M003", "M001"])
    assert matrix.samples == ("M001", "M003")


def test_genome_filter_restricts_rows(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog), genomes=["X:bin_3"])
    assert matrix.genomes == ("X:bin_3",)


def test_filtered_export_skips_the_round_trip_check(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog), taxonomy={"genus": "Faeciplasma"})
    assert matrix.filtered
    matrix.verify()


def test_mixing_levels_is_refused(catalog) -> None:
    with pytest.raises(CountsError):
        dense_matrix(catalog, list_matrix_sources(catalog))


def test_empty_selection_is_refused(catalog) -> None:
    with pytest.raises(CountsError):
        dense_matrix(catalog, [])


def test_micro_coordinates_align_to_the_matrix_columns(catalog) -> None:
    matrix = dense_matrix(catalog, _micro(catalog))
    coordinates = sample_coordinates(catalog, matrix.samples, level="micro")
    assert [row["sample"] for row in coordinates] == list(matrix.samples)
    assert coordinates[0]["microsample_id"] == "CRYO1-001"
    assert (coordinates[0]["x_coord"], coordinates[0]["y_coord"]) == (10.0, 20.0)
    assert (coordinates[0]["pixel_x"], coordinates[0]["pixel_y"]) == (1, 2)


def test_macro_coordinates_carry_sample_context(catalog) -> None:
    sources = list_matrix_sources(catalog, level="macro")
    matrix = dense_matrix(catalog, sources)
    coordinates = sample_coordinates(catalog, matrix.samples, level="macro")
    assert [row["sample"] for row in coordinates] == list(MACRO_SAMPLES)
    assert coordinates[0]["macrosample_id"] == "X01aF"


def test_a_column_with_no_metadata_still_gets_a_row(catalog) -> None:
    """LIB2 has no ENA accession, so it has no macrosample; it must not drop out."""
    coordinates = sample_coordinates(catalog, ["LIB2"], level="macro")
    assert len(coordinates) == 1
    assert coordinates[0]["sample"] == "LIB2"
    assert coordinates[0]["macrosample_id"] is None
