"""Downloads: integrity checks, manifests, and batch scripts. No network."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest
from rich.console import Console

from py3dtk.download import (
    DownloadJob,
    _GzipChecker,
    IntegrityError,
    destination_for_url,
    download_jobs,
    filename_from_url,
    write_batch_script,
)

PAYLOAD = gzip.compress(b"reads\n" * 100)
MD5 = hashlib.md5(PAYLOAD).hexdigest()


class _FakeResponse:
    def __init__(self, body: bytes, *, content_length: int | None = None) -> None:
        self._body = body
        self.headers = {}
        if content_length is not None:
            self.headers["content-length"] = str(content_length)

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


@pytest.fixture
def serve(monkeypatch):
    def _serve(body: bytes, *, content_length: int | None = None):
        monkeypatch.setattr(
            "py3dtk.download.requests.get",
            lambda url, **kwargs: _FakeResponse(body, content_length=content_length),
        )

    return _serve


def _job(tmp_path, *, md5=None, size=None, name="r_1.fastq.gz"):
    return DownloadJob(
        entry_type="microsample",
        id_field="microsample_id",
        id_value="M1",
        url=f"https://example.invalid/{name}",
        destination=tmp_path / name,
        md5=md5,
        expected_size=size,
    )


def _run(job, tmp_path):
    return download_jobs(
        [job], manifest_path=tmp_path / "manifest.jsonl", console=Console(quiet=True)
    )[0]


def test_downloads_and_records_a_sha256(serve, tmp_path) -> None:
    serve(PAYLOAD)
    result = _run(_job(tmp_path, md5=MD5, size=len(PAYLOAD)), tmp_path)
    assert result.status == "downloaded"
    assert result.checksum == hashlib.sha256(PAYLOAD).hexdigest()
    assert result.size == len(PAYLOAD)


def test_md5_mismatch_is_rejected(serve, tmp_path) -> None:
    serve(PAYLOAD)
    result = _run(_job(tmp_path, md5="0" * 32), tmp_path)
    assert result.status == "corrupt"
    assert "MD5 mismatch" in result.error
    assert not (tmp_path / "r_1.fastq.gz").exists()


def test_size_mismatch_against_ena_is_rejected(serve, tmp_path) -> None:
    serve(PAYLOAD)
    result = _run(_job(tmp_path, size=len(PAYLOAD) + 1), tmp_path)
    assert result.status == "corrupt"
    assert "ENA lists" in result.error


def test_truncated_response_is_rejected(serve, tmp_path) -> None:
    serve(PAYLOAD[:20], content_length=len(PAYLOAD))
    result = _run(_job(tmp_path), tmp_path)
    assert result.status == "corrupt"
    assert "truncated" in result.error


def test_corrupt_gzip_is_rejected_even_without_an_md5(serve, tmp_path) -> None:
    serve(PAYLOAD[:-30])
    result = _run(_job(tmp_path), tmp_path)
    assert result.status == "corrupt"


def test_existing_files_are_skipped_unless_overwritten(serve, tmp_path) -> None:
    serve(PAYLOAD)
    destination = tmp_path / "r_1.fastq.gz"
    destination.write_bytes(b"old")
    assert _run(_job(tmp_path, md5=MD5), tmp_path).status == "skipped_existing"

    result = download_jobs(
        [_job(tmp_path, md5=MD5)],
        manifest_path=tmp_path / "m.jsonl",
        overwrite=True,
        console=Console(quiet=True),
    )[0]
    assert result.status == "downloaded"
    assert destination.read_bytes() == PAYLOAD


def test_network_failure_is_reported_not_raised(monkeypatch, tmp_path) -> None:
    def boom(url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("py3dtk.download.requests.get", boom)
    result = _run(_job(tmp_path), tmp_path)
    assert result.status == "failed"
    assert "connection refused" in result.error


def test_every_job_appends_one_manifest_entry(serve, tmp_path) -> None:
    import json

    serve(PAYLOAD)
    manifest = tmp_path / "manifest.jsonl"
    download_jobs(
        [_job(tmp_path, md5=MD5, name="a.fastq.gz"), _job(tmp_path, name="b.fastq.gz")],
        manifest_path=manifest,
        console=Console(quiet=True),
    )
    entries = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert len(entries) == 2
    assert entries[0]["microsample_id"] == "M1"
    assert entries[0]["status"] == "downloaded"
    assert set(entries[0]) >= {"timestamp", "type", "url", "path", "checksum", "bytes"}


def test_unsupported_scheme_fails_cleanly(tmp_path) -> None:
    job = DownloadJob(
        "microsample", "microsample_id", "M1", "gopher://x/y.gz", tmp_path / "y.gz"
    )
    assert _run(job, tmp_path).status == "failed"


def test_batch_script_is_executable_and_verifies_md5(tmp_path) -> None:
    script = write_batch_script(
        tmp_path / "dl.sh", [_job(tmp_path, md5=MD5)], overwrite=False
    )
    body = script.read_text()
    assert script.stat().st_mode & 0o111
    assert body.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in body
    assert MD5 in body
    assert "MD5 mismatch" in body
    assert "if [ -f" in body, "non-overwrite scripts must skip existing files"


def test_batch_script_without_md5_still_downloads(tmp_path) -> None:
    body = write_batch_script(tmp_path / "dl.sh", [_job(tmp_path)]).read_text()
    assert "curl --fail --location" in body
    assert "md5_of" not in body.split("mkdir")[-1]


def test_filename_helpers() -> None:
    assert filename_from_url("https://x/a/b.fastq.gz", fallback="f") == "b.fastq.gz"
    assert filename_from_url("https://x/", fallback="f.gz") == "f.gz"
    assert destination_for_url(
        Path("/tmp"), "https://x/b.gz", fallback_name="f"
    ).name == "b.gz"


def test_gzip_checker_accepts_concatenated_members() -> None:
    checker = _GzipChecker()
    checker.update(gzip.compress(b"one") + gzip.compress(b"two"))
    checker.finish()


def test_gzip_checker_rejects_empty_and_truncated_streams() -> None:
    with pytest.raises(IntegrityError):
        _GzipChecker().finish()
    checker = _GzipChecker()
    checker.update(gzip.compress(b"data")[:-10])
    with pytest.raises(IntegrityError):
        checker.finish()
