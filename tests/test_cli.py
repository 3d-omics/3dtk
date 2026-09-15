"""The 3dtk command line."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from py3dtk.cli import app
from py3dtk.query import TARGETS

runner = CliRunner()

TARGET_NAMES = sorted(TARGETS)
FETCHABLE = ["macrosamples", "microsamples"]


def run(catalog, *args, **kwargs):
    return runner.invoke(app, ["--db", str(catalog), *args], **kwargs)


def test_version_is_reported() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_no_arguments_prints_a_catalogue_overview(catalog) -> None:
    result = run(catalog)
    assert result.exit_code == 0
    assert "3D'omics ToolKit" in result.stdout
    assert "Catalogue contents" in result.stdout
    for level in ("Experiments", "Microsamples", "Counts"):
        assert level in result.stdout


def test_help_lists_every_target() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for target in TARGET_NAMES:
        assert target in result.stdout


@pytest.mark.parametrize("target", TARGET_NAMES)
def test_every_target_supports_the_same_actions(catalog, target) -> None:
    help_text = run(catalog, target, "--help").stdout
    for action in ("query", "values", "stats", "fields"):
        assert action in help_text, f"{target} is missing {action}"


@pytest.mark.parametrize("target", TARGET_NAMES)
def test_query_emits_csv(catalog, target) -> None:
    result = run(catalog, target, "query", "--csv", "--limit", "1")
    assert result.exit_code == 0
    assert len(result.stdout.strip().splitlines()) >= 1


@pytest.mark.parametrize("target", TARGET_NAMES)
def test_stats_runs(catalog, target) -> None:
    assert run(catalog, target, "stats").exit_code == 0


@pytest.mark.parametrize("target", TARGET_NAMES)
def test_fields_lists_filterable_fields(catalog, target) -> None:
    result = run(catalog, target, "fields", "--csv")
    assert result.exit_code == 0
    assert "field,type,resolves_to" in result.stdout


def test_query_tsv_and_output_file(catalog, tmp_path) -> None:
    destination = tmp_path / "out.tsv"
    result = run(
        catalog, "genomes", "query", "--tsv", "--output-file", str(destination)
    )
    assert result.exit_code == 0
    header = destination.read_text().splitlines()[0]
    assert header.split("\t")[0] == "genome"


def test_csv_and_tsv_together_are_rejected(catalog) -> None:
    assert run(catalog, "genomes", "query", "--csv", "--tsv").exit_code == 2


def test_output_file_without_a_format_is_rejected(catalog, tmp_path) -> None:
    result = run(catalog, "genomes", "query", "--output-file", str(tmp_path / "x"))
    assert result.exit_code == 2


def test_filters_narrow_results(catalog) -> None:
    result = run(catalog, "specimens", "query", "--sex", "female", "--csv")
    rows = result.stdout.strip().splitlines()[1:]
    assert len(rows) == 1 and rows[0].startswith("X01")


def test_taxonomy_filter_accepts_a_bare_rank(catalog) -> None:
    result = run(catalog, "genomes", "query", "--genus", "Faeciplasma", "--csv")
    assert result.exit_code == 0
    assert len(result.stdout.strip().splitlines()) == 2


def test_class_filter_is_spelled_without_a_trailing_underscore(catalog) -> None:
    result = run(catalog, "genomes", "query", "--class", "Clostridia", "--csv")
    assert result.exit_code == 0
    assert "X:bin_1" in result.stdout


def test_bounding_box_options(catalog) -> None:
    result = run(
        catalog, "microsamples", "query",
        "--x-min", "20", "--x-max", "40", "--csv",
    )
    assert result.exit_code == 0
    assert len(result.stdout.strip().splitlines()) == 2


def test_boolean_flag_pairs(catalog) -> None:
    assert "X01aF" in run(catalog, "macrosamples", "query", "--has-ena", "--csv").stdout
    assert "X01aI" in run(catalog, "macrosamples", "query", "--no-ena", "--csv").stdout


def test_columns_preset_and_all(catalog) -> None:
    spatial = run(catalog, "microsamples", "query", "--columns", "spatial", "--csv")
    assert "x_coord" in spatial.stdout.splitlines()[0]
    every = run(catalog, "microsamples", "query", "--columns", "all", "--csv")
    assert "experiment_id" in every.stdout.splitlines()[0]


def test_unknown_column_is_a_usage_error(catalog) -> None:
    result = run(catalog, "genomes", "query", "--columns", "nope")
    assert result.exit_code == 2
    assert "--columns" in result.output


def test_unsafe_where_is_a_usage_error(catalog) -> None:
    result = run(catalog, "genomes", "query", "--where", "1=1; DROP TABLE genomes")
    assert result.exit_code == 2
    assert "--where" in result.output


def test_safe_where_is_accepted(catalog) -> None:
    result = run(catalog, "genomes", "query", "--where", "completeness > 90", "--csv")
    assert result.exit_code == 0
    assert len(result.stdout.strip().splitlines()) == 2


def test_values_requires_a_field(catalog) -> None:
    assert run(catalog, "genomes", "values").exit_code == 2


def test_values_reports_counts(catalog) -> None:
    result = run(catalog, "microsamples", "values", "--field", "sample_type", "--csv")
    assert "Positive,3" in result.stdout


def test_unknown_values_field_is_a_usage_error(catalog) -> None:
    result = run(catalog, "genomes", "values", "--field", "nope")
    assert result.exit_code == 2
    assert "--field" in result.output


@pytest.mark.parametrize("target", FETCHABLE)
def test_fetchable_targets_expose_fetch(catalog, target) -> None:
    assert "fetch" in run(catalog, target, "--help").stdout


@pytest.mark.parametrize("target", sorted(set(TARGET_NAMES) - set(FETCHABLE)))
def test_other_targets_do_not_expose_fetch(catalog, target) -> None:
    assert "fetch" not in run(catalog, target, "--help").stdout


def test_counts_matrices_lists_both_levels(catalog) -> None:
    result = run(catalog, "counts", "matrices", "--csv")
    assert result.exit_code == 0
    body = result.stdout
    assert "micro" in body and "macro" in body


def test_counts_export_restores_zeros(catalog) -> None:
    result = run(catalog, "counts", "export", "--level", "micro", "--csv")
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "genome,M001,M002,M003"
    assert "X:bin_2,0,0,0" in lines, "an all-zero genome must keep its row"


def test_counts_export_long_form(catalog) -> None:
    result = run(catalog, "counts", "export", "--level", "micro", "--long", "--csv")
    assert result.stdout.strip().splitlines()[0] == "genome,sample,count"
    assert len(result.stdout.strip().splitlines()) == 4


def test_counts_export_writes_a_coordinate_companion(catalog, tmp_path) -> None:
    matrix = tmp_path / "m.csv"
    coordinates = tmp_path / "coords.csv"
    result = run(
        catalog, "counts", "export", "--level", "micro",
        "--csv", "--output-file", str(matrix),
        "--coordinates", str(coordinates),
    )
    assert result.exit_code == 0
    matrix_columns = matrix.read_text().splitlines()[0].split(",")[1:]
    coordinate_rows = coordinates.read_text().strip().splitlines()[1:]
    assert len(coordinate_rows) == len(matrix_columns)
    assert "x_coord" in coordinates.read_text().splitlines()[0]


def test_counts_export_with_no_matching_matrix_is_a_usage_error(catalog) -> None:
    result = run(catalog, "counts", "export", "--cryosection-id", "nope")
    assert result.exit_code == 2


def test_database_info_reports_identity(catalog) -> None:
    result = run(catalog, "database", "info")
    assert result.exit_code == 0
    assert "Data version: 2026.01.01" in result.stdout
    assert "Schema version: 2" in result.stdout
    assert "SHA256:" in result.stdout


def test_database_info_flags_a_catalogue_that_is_not_the_pinned_release(catalog) -> None:
    assert "not the pinned" in run(catalog, "database", "info").stdout


def test_database_where_prints_the_resolved_path(catalog) -> None:
    result = run(catalog, "database", "where")
    assert result.exit_code == 0
    assert str(catalog) in result.stdout


def test_database_where_is_offline_and_explains_itself(monkeypatch) -> None:
    result = runner.invoke(app, ["database", "where"])
    assert result.exit_code == 1
    assert "3dtk database sync" in result.output


def test_missing_catalogue_is_a_usage_error(tmp_path) -> None:
    result = runner.invoke(app, ["--db", str(tmp_path / "absent.sqlite"), "genomes", "query"])
    assert result.exit_code == 2


def _stub_ena(monkeypatch, files_per_run: int = 2):
    from py3dtk.ena import EnaFile, EnaRun

    monkeypatch.setattr(
        "py3dtk.fetch.resolve_runs",
        lambda accessions, **kwargs: {
            accession: EnaRun(
                accession,
                tuple(
                    EnaFile(
                        f"https://ftp.invalid/{accession}_{index}.fastq.gz",
                        md5="a" * 32,
                        size=10,
                    )
                    for index in range(1, files_per_run + 1)
                ),
            )
            for accession in accessions
        },
    )


def test_fetch_writes_a_batch_script(catalog, tmp_path, monkeypatch) -> None:
    _stub_ena(monkeypatch)
    script = tmp_path / "dl.sh"
    result = run(
        catalog, "microsamples", "fetch",
        "--microsample-id", "CRYO1-001",
        "--script", str(script),
        "--output-dir", str(tmp_path),
        "--accept-terms",
    )
    assert result.exit_code == 0
    assert "queued 2 files" in result.output
    assert script.exists() and "md5_of" in script.read_text()


def test_fetch_reports_records_it_cannot_download(catalog, tmp_path, monkeypatch) -> None:
    _stub_ena(monkeypatch)
    result = run(
        catalog, "macrosamples", "fetch",
        "--data-type", "Metabolomics",
        "--output-dir", str(tmp_path),
        "--manifest-path", str(tmp_path / "manifest.jsonl"),
        "--accept-terms",
    )
    assert result.exit_code == 0
    assert "published to MetaboLights" in result.output
    assert "MTBLS1" in result.output


def test_unfetchable_records_are_recorded_even_when_nothing_downloads(
    catalog, tmp_path, monkeypatch
) -> None:
    """The manifest must account for every matched record, not only downloads."""
    import json

    _stub_ena(monkeypatch)
    manifest = tmp_path / "manifest.jsonl"
    result = run(
        catalog, "macrosamples", "fetch",
        "--data-type", "Metabolomics",
        "--output-dir", str(tmp_path),
        "--manifest-path", str(manifest),
        "--accept-terms",
    )
    assert result.exit_code == 0
    entries = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert [entry["status"] for entry in entries] == ["metabolights"]
    assert entries[0]["macrosample_id"] == "X01aI"


def test_batch_mode_writes_no_manifest(catalog, tmp_path, monkeypatch) -> None:
    _stub_ena(monkeypatch)
    manifest = tmp_path / "manifest.jsonl"
    run(
        catalog, "macrosamples", "fetch",
        "--data-type", "Metabolomics",
        "--script", str(tmp_path / "dl.sh"),
        "--manifest-path", str(manifest),
        "--accept-terms",
    )
    assert not manifest.exists()


def test_fetch_with_no_matches_says_so(catalog, tmp_path, monkeypatch) -> None:
    _stub_ena(monkeypatch)
    result = run(
        catalog, "microsamples", "fetch",
        "--microsample-id", "nope", "--output-dir", str(tmp_path), "--accept-terms",
    )
    assert result.exit_code == 0
    assert "No matching microsamples found." in result.output
