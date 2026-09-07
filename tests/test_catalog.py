"""Catalogue resolution and checksum-verified acquisition."""

from __future__ import annotations

import hashlib

import pytest

from threedtk import catalog as catalog_module
from threedtk.catalog import (
    PINNED_CATALOG,
    CatalogError,
    CatalogRelease,
    ChecksumMismatchError,
    catalog_source_label,
    download_catalog,
    file_sha256,
    resolve_catalog_path,
)

PAYLOAD = b"pretend sqlite bytes"


def _release(tmp_path) -> CatalogRelease:
    return CatalogRelease(
        data_version="2026.01.01",
        schema_version=2,
        filename="3domics-test.sqlite",
        sha256=hashlib.sha256(PAYLOAD).hexdigest(),
        url="https://example.invalid/catalog.sqlite",
        version_doi="10.5281/zenodo.1",
        concept_doi="10.5281/zenodo.0",
        license="CC-BY-4.0",
        size_bytes=len(PAYLOAD),
    )


def _chunks(_url):
    yield PAYLOAD[:5]
    yield PAYLOAD[5:]


def test_pinned_release_names_a_version_doi_not_the_concept() -> None:
    """A pinned build must never silently follow 'latest'."""
    assert PINNED_CATALOG.version_doi != PINNED_CATALOG.concept_doi
    assert PINNED_CATALOG.schema_version in {2}
    assert len(PINNED_CATALOG.sha256) == 64


def test_explicit_path_wins_over_everything(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("THREEDTK_DB", str(tmp_path / "env.sqlite"))
    assert resolve_catalog_path(tmp_path / "explicit.sqlite") == (
        tmp_path / "explicit.sqlite"
    )


def test_environment_variable_is_used_when_no_argument(tmp_path, monkeypatch) -> None:
    target = tmp_path / "env.sqlite"
    target.write_bytes(b"x")
    monkeypatch.setenv("THREEDTK_DB", str(target))
    assert resolve_catalog_path() == target.resolve()


def test_cached_catalogue_is_used_before_downloading(tmp_path, monkeypatch) -> None:
    release = _release(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / release.filename).write_bytes(PAYLOAD)
    monkeypatch.setattr(catalog_module, "cache_dir", lambda: cache)

    def _fail(*args, **kwargs):
        raise AssertionError("should not download when the cache is populated")

    monkeypatch.setattr(catalog_module, "download_catalog", _fail)
    assert resolve_catalog_path(release=release) == (cache / release.filename).resolve()


def test_bundled_resource_is_used_when_present(tmp_path, monkeypatch) -> None:
    bundled = tmp_path / "bundled.sqlite"
    bundled.write_bytes(PAYLOAD)
    monkeypatch.setattr(catalog_module, "cache_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(catalog_module, "bundled_catalog_path", lambda: bundled)
    assert resolve_catalog_path(release=_release(tmp_path)) == bundled.resolve()


def test_offline_resolution_raises_an_actionable_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalog_module, "cache_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(catalog_module, "bundled_catalog_path", lambda: None)
    with pytest.raises(CatalogError) as excinfo:
        resolve_catalog_path(auto_download=False, release=_release(tmp_path))
    message = str(excinfo.value)
    assert "3dtk database sync" in message and "THREEDTK_DB" in message


def test_download_verifies_the_checksum(tmp_path) -> None:
    release = _release(tmp_path)
    destination = tmp_path / release.filename
    assert download_catalog(destination, release=release, fetch=_chunks) == destination
    assert destination.read_bytes() == PAYLOAD


def test_a_bad_checksum_is_discarded_never_used(tmp_path) -> None:
    release = _release(tmp_path)
    destination = tmp_path / release.filename

    def corrupt(_url):
        yield b"not the expected bytes"

    with pytest.raises(ChecksumMismatchError):
        download_catalog(destination, release=release, fetch=corrupt)
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_a_failed_transfer_leaves_no_partial_file(tmp_path) -> None:
    release = _release(tmp_path)

    def failing(_url):
        yield PAYLOAD[:5]
        raise OSError("connection reset")

    with pytest.raises(OSError):
        download_catalog(tmp_path / release.filename, release=release, fetch=failing)
    assert list(tmp_path.glob("*")) == []


def test_existing_file_is_kept_unless_overwrite(tmp_path) -> None:
    release = _release(tmp_path)
    destination = tmp_path / release.filename
    destination.write_bytes(b"existing")

    download_catalog(destination, release=release, fetch=_chunks)
    assert destination.read_bytes() == b"existing"

    download_catalog(destination, release=release, fetch=_chunks, overwrite=True)
    assert destination.read_bytes() == PAYLOAD


def test_file_sha256_matches_hashlib(tmp_path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(PAYLOAD)
    assert file_sha256(path) == hashlib.sha256(PAYLOAD).hexdigest()


def test_source_label_identifies_where_the_catalogue_came_from(
    tmp_path, monkeypatch
) -> None:
    release = _release(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    cached = cache / release.filename
    cached.write_bytes(PAYLOAD)
    monkeypatch.setattr(catalog_module, "cache_dir", lambda: cache)
    monkeypatch.setattr(catalog_module, "bundled_catalog_path", lambda: None)

    assert catalog_source_label(cached, release) == "cache"
    other = tmp_path / "other.sqlite"
    other.write_bytes(PAYLOAD)
    assert catalog_source_label(other, release) == "custom"
    monkeypatch.setenv("THREEDTK_DB", str(other))
    assert catalog_source_label(other, release) == "environment (THREEDTK_DB)"
