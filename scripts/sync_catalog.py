#!/usr/bin/env python3
"""Pin or refresh the 3D'omics catalogue from its Zenodo concept.

Two jobs, both maintainer-time (never runtime):

``--pin`` resolves a release under the concept and rewrites
``PINNED_CATALOG`` in ``src/py3dtk/catalog.py`` to match. This is how a new
``data_version`` is adopted.

``--download`` fetches the resolved release into the user cache (or
``--output``), which is what ``3dtk database sync`` does at runtime.

Either way the artefact is verified against its ``.sha256`` sidecar before it is
used, and its ``schema_version`` is checked against
``SUPPORTED_SCHEMA_VERSIONS``. A pinned build never follows "latest" by
accident: without ``--data-version`` this resolves the newest published release
and *tells you* which one it picked.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from py3dtk.catalog import (  # noqa: E402
    CONCEPT_RECID,
    PINNED_CATALOG,
    cached_catalog_path,
)
from py3dtk.query import (  # noqa: E402
    SUPPORTED_SCHEMA_VERSIONS,
    UnsupportedSchemaVersionError,
    read_catalog_meta,
    validate_catalog_schema,
)

DEFAULT_ZENODO_URL = "https://zenodo.org"
CATALOG_MODULE = ROOT / "src" / "py3dtk" / "catalog.py"


class SyncError(RuntimeError):
    """Raised when a catalogue cannot be resolved, verified, or adopted."""


@dataclass(frozen=True)
class ResolvedRelease:
    data_version: str
    schema_version: int | None
    filename: str
    sha256: str
    url: str
    version_doi: str
    concept_doi: str
    size_bytes: int


def select_record(records: dict, data_version: str | None = None) -> dict:
    """Pick a pinned ``data_version``, or the latest published release."""
    hits = records.get("hits", {}).get("hits", [])
    if not hits:
        raise SyncError("No records found under the Zenodo concept.")
    if data_version:
        for hit in hits:
            if str(hit.get("metadata", {}).get("version")) == str(data_version):
                return hit
        raise SyncError(f"No Zenodo version {data_version} found under the concept.")

    def sort_key(hit: dict) -> tuple[str, str]:
        meta = hit.get("metadata", {})
        return (str(meta.get("publication_date", "")), str(meta.get("version", "")))

    return sorted(hits, key=sort_key)[-1]


def find_files(record: dict) -> tuple[dict, dict | None]:
    """Return the ``(.sqlite, .sha256-or-None)`` file entries from a record."""
    sqlite_file = sha_file = None
    for entry in record.get("files", []):
        name = _file_name(entry)
        if name.endswith(".sqlite"):
            sqlite_file = entry
        elif name.endswith(".sha256"):
            sha_file = entry
    if sqlite_file is None:
        raise SyncError("Selected Zenodo record has no .sqlite file.")
    return sqlite_file, sha_file


def verify_sha256(data: bytes, sidecar_text: str, *, name: str) -> str:
    """Verify bytes against a ``.sha256`` sidecar, returning the digest."""
    expected = sidecar_text.split()[0].strip().lower() if sidecar_text.strip() else ""
    if not expected:
        raise SyncError(f"Empty checksum sidecar for {name}.")
    actual = hashlib.sha256(data).hexdigest()
    if expected != actual:
        raise SyncError(
            f"Checksum mismatch for {name}: expected {expected}, got {actual}."
        )
    return actual


def resolve_release(
    *,
    data_version: str | None,
    concept_recid: str,
    zenodo_url: str,
    fetch_json,
) -> tuple[ResolvedRelease, dict, dict | None]:
    """Resolve which release to adopt, without downloading the artefact."""
    # Zenodo caps unauthenticated page size at 25; sort newest-first so the
    # latest published version is always on the first page.
    url = (
        f"{zenodo_url.rstrip('/')}/api/records"
        f"?q=conceptrecid:{concept_recid}&all_versions=true&size=25&sort=mostrecent"
    )
    record = select_record(fetch_json(url), data_version)
    sqlite_file, sha_file = find_files(record)
    resolved = ResolvedRelease(
        data_version=str(record.get("metadata", {}).get("version") or "unknown"),
        schema_version=None,
        filename=_file_name(sqlite_file),
        sha256="",
        url=_file_url(sqlite_file) or "",
        version_doi=str(record.get("doi") or ""),
        concept_doi=str(
            record.get("conceptdoi") or PINNED_CATALOG.concept_doi
        ),
        size_bytes=int(sqlite_file.get("size") or 0),
    )
    return resolved, sqlite_file, sha_file


def fetch_and_verify(
    resolved: ResolvedRelease,
    sqlite_file: dict,
    sha_file: dict | None,
    *,
    fetch_bytes,
    progress=None,
) -> tuple[bytes, ResolvedRelease]:
    """Download the artefact, verify it, and fill in its measured identity."""
    url = _file_url(sqlite_file)
    if not url:
        raise SyncError("Selected .sqlite file has no download URL.")
    payload = fetch_bytes(url)

    if sha_file is not None:
        sidecar_url = _file_url(sha_file)
        sidecar = fetch_bytes(sidecar_url).decode("utf-8") if sidecar_url else ""
        digest = verify_sha256(payload, sidecar, name=resolved.filename)
        _emit(progress, "Checksum verified against the .sha256 sidecar.")
    else:
        digest = hashlib.sha256(payload).hexdigest()
        _emit(
            progress,
            "Warning: record has no .sha256 sidecar; recording the computed digest.",
        )

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    try:
        try:
            validate_catalog_schema(temporary)
        except UnsupportedSchemaVersionError as exc:
            raise SyncError(
                f"{exc} Update the readers and SUPPORTED_SCHEMA_VERSIONS "
                f"(currently {sorted(SUPPORTED_SCHEMA_VERSIONS)}), or pin a "
                "compatible release with --data-version."
            ) from exc
        meta = read_catalog_meta(temporary)
    finally:
        temporary.unlink(missing_ok=True)

    from dataclasses import replace

    return payload, replace(
        resolved,
        sha256=digest,
        data_version=meta.get("data_version", resolved.data_version),
        schema_version=int(meta["schema_version"]) if "schema_version" in meta else None,
        size_bytes=len(payload),
    )


def rewrite_pin(release: ResolvedRelease, *, module_path: Path = CATALOG_MODULE) -> None:
    """Rewrite ``PINNED_CATALOG`` in ``catalog.py`` to name ``release``."""
    source = module_path.read_text(encoding="utf-8")
    block = f'''PINNED_CATALOG = CatalogRelease(
    data_version="{release.data_version}",
    schema_version={release.schema_version or PINNED_CATALOG.schema_version},
    filename="{release.filename}",
    sha256="{release.sha256}",
    url=(
        "{release.url}"
    ),
    version_doi="{release.version_doi}",
    concept_doi="{release.concept_doi}",
    license="{PINNED_CATALOG.license}",
    size_bytes={release.size_bytes},
)'''
    pattern = re.compile(r"PINNED_CATALOG = CatalogRelease\(.*?\n\)", re.DOTALL)
    if not pattern.search(source):
        raise SyncError(f"Could not find PINNED_CATALOG in {module_path}.")
    module_path.write_text(pattern.sub(block, source, count=1), encoding="utf-8")


def _file_name(entry: dict) -> str:
    return str(entry.get("key") or entry.get("filename") or "")


def _file_url(entry: dict) -> str | None:
    links = entry.get("links", {})
    return links.get("download") or links.get("self")


def _emit(progress, message: str) -> None:
    if progress is not None:
        progress(message)


def _requests_fetchers():
    import requests

    def fetch_json(url: str):
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.json()

    def fetch_bytes(url: str) -> bytes:
        response = requests.get(url, timeout=600)
        response.raise_for_status()
        return response.content

    return fetch_json, fetch_bytes


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-version",
        default=None,
        help="Pin a specific data_version (default: the latest published release).",
    )
    parser.add_argument(
        "--pin",
        action="store_true",
        help="Rewrite PINNED_CATALOG in src/py3dtk/catalog.py to the resolved release.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Write the verified catalogue to --output (default: the user cache).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the catalogue with --download.",
    )
    parser.add_argument(
        "--concept-recid",
        default=CONCEPT_RECID,
        help=f"Zenodo catalogue concept record id. Default: {CONCEPT_RECID}.",
    )
    parser.add_argument(
        "--zenodo-url",
        default=DEFAULT_ZENODO_URL,
        help=f"Zenodo base URL. Default: {DEFAULT_ZENODO_URL}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and report the release; download and write nothing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    fetch_json, fetch_bytes = _requests_fetchers()

    resolved, sqlite_file, sha_file = resolve_release(
        data_version=args.data_version,
        concept_recid=args.concept_recid,
        zenodo_url=args.zenodo_url,
        fetch_json=fetch_json,
    )
    print(
        f"Resolved release {resolved.data_version} "
        f"(DOI {resolved.version_doi or 'n/a'}); file {resolved.filename}"
    )
    if args.data_version is None:
        print("Note: resolved the latest published release, not a pinned version.")

    if args.dry_run:
        print("Dry run: nothing downloaded or written.")
        return 0

    payload, release = fetch_and_verify(
        resolved, sqlite_file, sha_file, fetch_bytes=fetch_bytes, progress=print
    )
    print(f"data_version={release.data_version}")
    print(f"schema_version={release.schema_version}")
    print(f"sha256={release.sha256}")

    if args.download:
        output = args.output or cached_catalog_path()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        print(f"Wrote verified catalogue to {output}")

    if args.pin:
        rewrite_pin(release)
        print(f"Rewrote PINNED_CATALOG in {CATALOG_MODULE}")

    if not (args.download or args.pin):
        print("Nothing written. Pass --pin and/or --download.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncError as exc:
        print(f"Catalogue sync failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
