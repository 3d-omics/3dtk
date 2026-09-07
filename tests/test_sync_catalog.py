"""The maintainer-time catalogue sync script. No network."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sync_catalog", ROOT / "scripts" / "sync_catalog.py"
)
sync_catalog = importlib.util.module_from_spec(spec)
sys.modules["sync_catalog"] = sync_catalog
spec.loader.exec_module(sync_catalog)


def _records(*versions: str) -> dict:
    return {
        "hits": {
            "hits": [
                {
                    "doi": f"10.5281/zenodo.{index}",
                    "conceptdoi": "10.5281/zenodo.0",
                    "metadata": {"version": version, "publication_date": f"2026-01-0{index+1}"},
                    "files": [
                        {
                            "key": f"3domics-{version}.sqlite",
                            "size": 100,
                            "links": {"download": f"https://z/{version}.sqlite"},
                        },
                        {
                            "key": f"3domics-{version}.sqlite.sha256",
                            "links": {"download": f"https://z/{version}.sha256"},
                        },
                    ],
                }
                for index, version in enumerate(versions)
            ]
        }
    }


def test_selects_the_latest_release_by_default() -> None:
    record = sync_catalog.select_record(_records("2026.01.01", "2026.02.02"))
    assert record["metadata"]["version"] == "2026.02.02"


def test_pins_an_explicit_version() -> None:
    record = sync_catalog.select_record(
        _records("2026.01.01", "2026.02.02"), "2026.01.01"
    )
    assert record["metadata"]["version"] == "2026.01.01"


def test_unknown_version_is_an_error() -> None:
    with pytest.raises(sync_catalog.SyncError):
        sync_catalog.select_record(_records("2026.01.01"), "1999.01.01")


def test_empty_concept_is_an_error() -> None:
    with pytest.raises(sync_catalog.SyncError):
        sync_catalog.select_record({"hits": {"hits": []}})


def test_finds_the_sqlite_and_its_sidecar() -> None:
    record = sync_catalog.select_record(_records("2026.01.01"))
    sqlite_file, sha_file = sync_catalog.find_files(record)
    assert sqlite_file["key"].endswith(".sqlite")
    assert sha_file["key"].endswith(".sha256")


def test_record_without_a_sqlite_is_an_error() -> None:
    with pytest.raises(sync_catalog.SyncError):
        sync_catalog.find_files({"files": [{"key": "readme.txt"}]})


def test_checksum_verification_accepts_a_matching_sidecar() -> None:
    payload = b"bytes"
    digest = hashlib.sha256(payload).hexdigest()
    assert sync_catalog.verify_sha256(
        payload, f"{digest}  3domics.sqlite\n", name="x"
    ) == digest


def test_checksum_mismatch_is_an_error() -> None:
    with pytest.raises(sync_catalog.SyncError):
        sync_catalog.verify_sha256(b"bytes", "0" * 64, name="x")


def test_empty_sidecar_is_an_error() -> None:
    with pytest.raises(sync_catalog.SyncError):
        sync_catalog.verify_sha256(b"bytes", "   ", name="x")


def test_resolve_release_reports_what_it_picked() -> None:
    resolved, sqlite_file, sha_file = sync_catalog.resolve_release(
        data_version=None,
        concept_recid="1",
        zenodo_url="https://z",
        fetch_json=lambda url: _records("2026.01.01", "2026.02.02"),
    )
    assert resolved.data_version == "2026.02.02"
    assert resolved.url == "https://z/2026.02.02.sqlite"
    assert sha_file is not None


def test_fetch_and_verify_reads_identity_from_the_catalogue(tmp_path) -> None:
    from conftest import build_catalog

    built = build_catalog(tmp_path / "built.sqlite")
    payload = built.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    resolved, sqlite_file, sha_file = sync_catalog.resolve_release(
        data_version=None,
        concept_recid="1",
        zenodo_url="https://z",
        fetch_json=lambda url: _records("2026.01.01"),
    )

    def fetch_bytes(url: str) -> bytes:
        return payload if url.endswith(".sqlite") else digest.encode()

    _, release = sync_catalog.fetch_and_verify(
        resolved, sqlite_file, sha_file, fetch_bytes=fetch_bytes
    )
    assert release.sha256 == digest
    assert release.data_version == "2026.01.01"
    assert release.schema_version == 2


def test_unsupported_schema_version_is_refused(tmp_path) -> None:
    from conftest import build_catalog

    built = build_catalog(tmp_path / "future.sqlite", schema_version="99")
    payload = built.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    resolved, sqlite_file, sha_file = sync_catalog.resolve_release(
        data_version=None,
        concept_recid="1",
        zenodo_url="https://z",
        fetch_json=lambda url: _records("2026.01.01"),
    )

    with pytest.raises(sync_catalog.SyncError) as excinfo:
        sync_catalog.fetch_and_verify(
            resolved,
            sqlite_file,
            sha_file,
            fetch_bytes=lambda url: payload if url.endswith(".sqlite") else digest.encode(),
        )
    assert "SUPPORTED_SCHEMA_VERSIONS" in str(excinfo.value)


def test_rewrite_pin_updates_the_module(tmp_path) -> None:
    module = tmp_path / "catalog.py"
    module.write_text(
        'HEADER = 1\n\n'
        'PINNED_CATALOG = CatalogRelease(\n'
        '    data_version="old",\n'
        '    sha256="old",\n'
        ')\n\nFOOTER = 2\n',
        encoding="utf-8",
    )
    release = sync_catalog.ResolvedRelease(
        data_version="2026.09.09",
        schema_version=2,
        filename="3domics-2026.09.09.sqlite",
        sha256="a" * 64,
        url="https://zenodo.org/x/content",
        version_doi="10.5281/zenodo.9",
        concept_doi="10.5281/zenodo.0",
        size_bytes=123,
    )
    sync_catalog.rewrite_pin(release, module_path=module)
    body = module.read_text()
    assert 'data_version="2026.09.09"' in body
    assert '"a" * 64' not in body and "a" * 64 in body
    assert body.startswith("HEADER = 1") and body.rstrip().endswith("FOOTER = 2")


def test_rewrite_pin_refuses_a_module_without_the_block(tmp_path) -> None:
    module = tmp_path / "catalog.py"
    module.write_text("nothing here\n", encoding="utf-8")
    with pytest.raises(sync_catalog.SyncError):
        sync_catalog.rewrite_pin(
            sync_catalog.ResolvedRelease("v", 2, "f", "s", "u", "d", "c", 1),
            module_path=module,
        )


def test_dry_run_writes_nothing(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        sync_catalog,
        "_requests_fetchers",
        lambda: (lambda url: _records("2026.01.01"), lambda url: b""),
    )
    assert sync_catalog.main(["--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Dry run" in output
    assert "latest published release, not a pinned version" in output
