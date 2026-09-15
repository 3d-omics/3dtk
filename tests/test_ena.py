"""ENA Portal API resolution: parsing, batching, and caching. No network."""

from __future__ import annotations

import pytest

from py3dtk.ena import (
    DEFAULT_BATCH_SIZE,
    EnaError,
    parse_filereport,
    resolve_runs,
    run_browser_url,
)

RESPONSE = (
    "run_accession\texperiment_accession\tsample_accession\tfastq_ftp\tfastq_md5\t"
    "fastq_bytes\tsubmitted_ftp\n"
    "ERR1\tERX1\tSAMEA1\t"
    "ftp.sra.ebi.ac.uk/vol1/fastq/ERR1/ERR1_1.fastq.gz;"
    "ftp.sra.ebi.ac.uk/vol1/fastq/ERR1/ERR1_2.fastq.gz\t"
    "aaa;bbb\t100;200\tftp.sra.ebi.ac.uk/vol1/run/ERR1/x.fq.gz\n"
)


def test_parses_paired_end_files_with_md5s_and_sizes() -> None:
    run = parse_filereport(RESPONSE)[0]
    assert run.run_accession == "ERR1"
    assert run.sample_accession == "SAMEA1"
    assert [f.filename for f in run.files] == ["ERR1_1.fastq.gz", "ERR1_2.fastq.gz"]
    assert [f.md5 for f in run.files] == ["aaa", "bbb"]
    assert [f.size for f in run.files] == [100, 200]


def test_qualifies_scheme_less_paths_as_https_by_default() -> None:
    run = parse_filereport(RESPONSE)[0]
    assert run.files[0].url.startswith("https://ftp.sra.ebi.ac.uk/")


def test_ftp_protocol_is_available() -> None:
    run = parse_filereport(RESPONSE, protocol="ftp")[0]
    assert run.files[0].url.startswith("ftp://ftp.sra.ebi.ac.uk/")


def test_empty_response_yields_no_runs() -> None:
    assert parse_filereport("") == []
    assert parse_filereport("run_accession\tfastq_ftp\n") == []


def test_unexpected_header_is_reported() -> None:
    with pytest.raises(EnaError):
        parse_filereport("nonsense\nvalues\n")


def test_a_run_with_no_files_parses_without_error() -> None:
    text = "run_accession\tfastq_ftp\tfastq_md5\nERR9\t\t\n"
    run = parse_filereport(text)[0]
    assert run.run_accession == "ERR9" and run.files == ()


def test_resolve_batches_accessions_into_few_requests() -> None:
    calls: list[dict] = []

    def fake_fetch(url, data):
        calls.append(data)
        accessions = [
            part.split('"')[1] for part in data["query"].split(" OR ")
        ]
        lines = ["run_accession\tfastq_ftp\tfastq_md5\tfastq_bytes"]
        lines += [f"{a}\tftp.x/{a}_1.fq.gz\tmd5{a}\t10" for a in accessions]
        return "\n".join(lines) + "\n"

    accessions = [f"ERR{index}" for index in range(450)]
    runs = resolve_runs(accessions, fetch=fake_fetch)

    assert len(runs) == 450
    assert len(calls) == 3  # 450 accessions at 200 per batch
    assert all(len(call["query"].split(" OR ")) <= DEFAULT_BATCH_SIZE for call in calls)


def test_resolve_uses_the_search_endpoint_with_an_or_query() -> None:
    seen: list[str] = []

    def fake_fetch(url, data):
        seen.append(url)
        assert data["result"] == "read_run"
        assert data["query"] == 'run_accession="ERR1" OR run_accession="ERR2"'
        return RESPONSE

    resolve_runs(["ERR1", "ERR2"], fetch=fake_fetch)
    assert seen == ["https://www.ebi.ac.uk/ena/portal/api/search"]


def test_cache_prevents_a_second_request() -> None:
    cache: dict = {}
    calls = []

    def fake_fetch(url, data):
        calls.append(data)
        return RESPONSE

    resolve_runs(["ERR1"], fetch=fake_fetch, cache=cache)
    resolve_runs(["ERR1"], fetch=fake_fetch, cache=cache)
    assert len(calls) == 1
    assert "ERR1" in cache


def test_duplicate_and_blank_accessions_are_ignored() -> None:
    calls = []

    def fake_fetch(url, data):
        calls.append(data)
        return RESPONSE

    resolve_runs(["ERR1", "ERR1", "", "  "], fetch=fake_fetch)
    assert calls[0]["query"] == 'run_accession="ERR1"'


def test_unknown_accessions_are_simply_absent() -> None:
    runs = resolve_runs(["ERR1", "ERRMISSING"], fetch=lambda url, data: RESPONSE)
    assert set(runs) == {"ERR1"}


def test_unsupported_protocol_is_rejected() -> None:
    with pytest.raises(EnaError):
        resolve_runs(["ERR1"], protocol="gopher", fetch=lambda url, data: RESPONSE)


def test_browser_url_matches_the_catalogue_format() -> None:
    assert run_browser_url("ERR15114245") == (
        "https://www.ebi.ac.uk/ena/browser/view/ERR15114245"
    )
