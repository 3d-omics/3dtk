"""The public Python API."""

from __future__ import annotations

import pytest

import py3dtk
from py3dtk.api import CountCell, Database, Genome, Microsample


def test_database_exposes_every_collection(catalog) -> None:
    with Database(catalog) as db:
        assert {
            name: getattr(db, name).count()
            for name in (
                "experiments", "specimens", "macrosamples", "cryosections",
                "microsamples", "genomes", "counts",
            )
        } == {
            "experiments": 2, "specimens": 2, "macrosamples": 2, "cryosections": 1,
            "microsamples": 4, "genomes": 3, "counts": 4,
        }


def test_records_are_typed(catalog) -> None:
    with Database(catalog) as db:
        assert isinstance(db.microsamples.query(limit=1)[0], Microsample)
        assert isinstance(db.genomes.query(limit=1)[0], Genome)
        assert isinstance(db.counts.query(limit=1)[0], CountCell)


def test_class_field_is_exposed_as_class_(catalog) -> None:
    """`class` is a Python keyword, so the dataclass field is `class_`."""
    with Database(catalog) as db:
        genome = db.genomes.query(genome="X:bin_1", columns="taxonomy")[0]
    assert genome.class_ == "Clostridia"


def test_sequence_filters_behave_like_comma_separated_values(catalog) -> None:
    with Database(catalog) as db:
        assert db.specimens.count(sex=["female", "male"]) == 2
        assert db.genomes.count(quality=["high", "low"]) == 2


def test_boolean_filters_are_passed_through(catalog) -> None:
    with Database(catalog) as db:
        assert db.macrosamples.count(has_ena=True) == 1
        assert db.macrosamples.count(has_ena=False) == 1


def test_columns_accept_a_sequence(catalog) -> None:
    with Database(catalog) as db:
        rows = db.genomes.query(columns=["genome", "genus"], limit=1)
    assert rows[0].genome and rows[0].genus and rows[0].completeness is None


def test_values_returns_counts_in_descending_order(catalog) -> None:
    with Database(catalog) as db:
        result = db.microsamples.values("sample_type")
    assert result.field == "sample_type"
    assert result.rows[0].value == "Positive"
    assert result.rows[0].count == 3


def test_stats_summarise_matching_records(catalog) -> None:
    with Database(catalog) as db:
        stats = db.genomes.stats()
    assert stats.summary["matched_genomes"] == 3
    assert any(b.title == "Quality distribution" for b in stats.breakdowns)


def test_stats_on_no_matches_reports_an_empty_message(catalog) -> None:
    with Database(catalog) as db:
        stats = db.genomes.stats(genus="Nonexistent")
    assert stats.empty_message == "No matching genomes found."
    assert stats.breakdowns == ()


def test_counts_export_restores_zeros_and_verifies(catalog) -> None:
    with Database(catalog) as db:
        matrix = db.counts.export(level="micro")
    assert matrix.genomes == ("X:bin_1", "X:bin_2", "X:bin_3")
    assert matrix.cell("X:bin_2", "M001") == 0
    assert matrix.cell("X:bin_1", "M001") == 10.5


def test_counts_coordinates_align_to_the_matrix(catalog) -> None:
    with Database(catalog) as db:
        matrix = db.counts.export(level="micro")
        coordinates = db.counts.coordinates(matrix)
    assert [row["sample"] for row in coordinates] == list(matrix.samples)


def test_counts_matrices_lists_sources(catalog) -> None:
    with Database(catalog) as db:
        assert len(db.counts.matrices(level="micro")) == 1


def test_fetch_is_available_only_where_files_exist(catalog) -> None:
    with Database(catalog) as db:
        assert hasattr(db.microsamples, "fetch")
        assert hasattr(db.macrosamples, "fetch")
        assert not hasattr(db.genomes, "fetch")


def test_fetch_writes_a_batch_script_without_downloading(
    catalog, tmp_path, monkeypatch
) -> None:
    from py3dtk.ena import EnaFile, EnaRun

    monkeypatch.setattr(
        "py3dtk.fetch.resolve_runs",
        lambda accessions, **kwargs: {
            accession: EnaRun(
                accession,
                (EnaFile(f"https://x/{accession}_1.fastq.gz", md5="aaa", size=1),),
            )
            for accession in accessions
        },
    )

    script = tmp_path / "download.sh"
    with Database(catalog) as db:
        summary = db.microsamples.fetch(
            microsample_id="CRYO1-001", batch=script, output_dir=tmp_path
        )

    assert summary.batch_script == script
    assert summary.matched_count == 1
    assert summary.queued_count == 1
    body = script.read_text()
    assert body.startswith("#!/usr/bin/env bash")
    assert "md5_of" in body, "batch scripts must re-verify the MD5 ENA published"


def test_meta_reports_catalogue_identity(catalog) -> None:
    with Database(catalog) as db:
        assert db.meta["schema_version"] == "2"


def test_closed_database_refuses_queries(catalog) -> None:
    db = Database(catalog)
    db.close()
    with pytest.raises(RuntimeError):
        db.genomes.query()


def test_missing_catalogue_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        Database(tmp_path / "absent.sqlite")


def test_public_names_are_exported() -> None:
    for name in ("Database", "Genome", "Microsample", "PINNED_CATALOG", "__version__"):
        assert hasattr(py3dtk, name)
