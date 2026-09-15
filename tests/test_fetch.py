"""Fetch planning: accession resolution, and honest reporting of what cannot be fetched."""

from __future__ import annotations

import pytest

from py3dtk.ena import EnaFile, EnaRun
from py3dtk.fetch import format_bytes, plan_fetch
from py3dtk.query import QueryValidationError


def _resolver(accessions, **kwargs):
    return {
        accession: EnaRun(
            run_accession=accession,
            files=(
                EnaFile(f"https://ftp.x/{accession}_1.fastq.gz", md5="aaa", size=10),
                EnaFile(f"https://ftp.x/{accession}_2.fastq.gz", md5="bbb", size=20),
            ),
        )
        for accession in accessions
    }


def test_plans_paired_end_jobs_per_record(catalog, tmp_path) -> None:
    plan = plan_fetch(
        catalog, "microsamples", filters={"microsample_id": "CRYO1-001"},
        output_dir=tmp_path, resolver=_resolver,
    )
    assert plan.matched_count == 1
    assert len(plan.jobs) == 2
    assert plan.total_bytes == 30
    assert plan.jobs[0].destination.parent.name == "CRYO1-001"
    assert plan.jobs[0].md5 == "aaa"


def test_records_without_an_accession_are_reported_not_dropped(catalog, tmp_path) -> None:
    plan = plan_fetch(
        catalog, "microsamples", filters={"microsample_id": "ORPHAN-001"},
        output_dir=tmp_path, resolver=_resolver,
    )
    assert plan.matched_count == 1
    assert plan.jobs == ()
    assert plan.reasons() == {"no_accession": 1}


def test_metabolomics_macrosamples_surface_their_metabolights_accession(
    catalog, tmp_path
) -> None:
    plan = plan_fetch(
        catalog, "macrosamples", filters={"data_type": "Metabolomics"},
        output_dir=tmp_path, resolver=_resolver,
    )
    assert plan.reasons() == {"metabolights": 1}
    assert plan.unfetchable[0].detail == "MTBLS1"


def test_accessions_ena_does_not_know_are_reported(catalog, tmp_path) -> None:
    plan = plan_fetch(
        catalog, "microsamples", filters={"microsample_id": "CRYO1-001"},
        output_dir=tmp_path, resolver=lambda accessions, **kwargs: {},
    )
    assert plan.reasons() == {"unresolved_accession": 1}
    assert plan.unfetchable[0].detail == "ERR1"


def test_no_matches_yields_an_empty_plan(catalog, tmp_path) -> None:
    plan = plan_fetch(
        catalog, "microsamples", filters={"microsample_id": "nope"},
        output_dir=tmp_path, resolver=_resolver,
    )
    assert plan.matched_count == 0 and plan.jobs == ()


def test_unfetchable_targets_are_rejected(catalog) -> None:
    with pytest.raises(QueryValidationError):
        plan_fetch(catalog, "genomes")


def test_accessions_are_resolved_in_one_batched_call(catalog, tmp_path) -> None:
    calls = []

    def counting_resolver(accessions, **kwargs):
        calls.append(list(accessions))
        return _resolver(accessions)

    plan = plan_fetch(
        catalog, "microsamples", filters={"has_sequencing": True},
        output_dir=tmp_path, resolver=counting_resolver,
    )
    assert len(calls) == 1
    assert sorted(calls[0]) == ["ERR1", "ERR2", "ERR3"]
    assert len(plan.jobs) == 6


@pytest.mark.parametrize(
    ("size", "expected"),
    [(0, "0 B"), (512, "512 B"), (2048, "2.0 KB"), (5 * 1024**3, "5.0 GB")],
)
def test_format_bytes(size, expected) -> None:
    assert format_bytes(size) == expected
