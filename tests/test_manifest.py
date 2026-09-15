"""The append-only download manifest."""

from __future__ import annotations

import json

from py3dtk.manifest import ManifestEntry, append_manifest_entry


def _entry(**overrides):
    payload = dict(
        entry_type="microsample",
        id_field="microsample_id",
        id_value="M1",
        url="https://x/a.gz",
        path="/tmp/a.gz",
        checksum="abc",
        status="downloaded",
        size=10,
    )
    payload.update(overrides)
    return ManifestEntry(**payload)


def test_entries_are_appended_one_json_object_per_line(tmp_path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    append_manifest_entry(manifest, _entry())
    append_manifest_entry(manifest, _entry(id_value="M2", status="failed"))

    lines = manifest.read_text().splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["microsample_id"] for line in lines] == ["M1", "M2"]


def test_entry_records_the_expected_fields(tmp_path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    append_manifest_entry(manifest, _entry())
    payload = json.loads(manifest.read_text())
    assert payload["type"] == "microsample"
    assert payload["bytes"] == 10
    assert payload["checksum"] == "abc"
    assert payload["timestamp"].endswith("Z")


def test_parent_directories_are_created(tmp_path) -> None:
    manifest = tmp_path / "nested" / "dir" / "manifest.jsonl"
    append_manifest_entry(manifest, _entry())
    assert manifest.exists()


def test_missing_url_entries_are_recorded(tmp_path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    append_manifest_entry(
        manifest, _entry(url=None, path=None, checksum=None, size=None, status="no_accession")
    )
    payload = json.loads(manifest.read_text())
    assert payload["url"] is None and payload["status"] == "no_accession"
