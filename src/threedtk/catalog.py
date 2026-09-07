"""Catalogue location, acquisition, and identity.

``3dtk`` is a consumer of a published artefact. This module owns the four-step
resolution order that decides *which* SQLite file a command reads, and the
pinned identity of the release this version of ``3dtk`` was built against.

Resolution order (:func:`resolve_catalog_path`):

1. an explicit ``--db`` / ``path=`` argument,
2. the ``THREEDTK_DB`` environment variable,
3. the user cache, populated by ``3dtk database sync`` or a lazy first-use
   download,
4. a bundled package resource, if one was shipped.

The shipped default is step 3: the wheel carries no catalogue and the 59 MB
artefact is fetched once, verified against a pinned SHA-256, and cached. Step 4
exists so that bundling becomes a packaging decision -- drop a ``.sqlite`` into
``src/threedtk/data/`` and it is found without touching the query layer.

A pinned build never silently follows "latest". :data:`PINNED_CATALOG` names one
immutable Zenodo *version* record; the concept DOI is for citation only.
"""

from __future__ import annotations

import atexit
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
from importlib import resources
import os
from pathlib import Path
from typing import Callable, Iterable

from platformdirs import user_cache_dir

APP_NAME = "3dtk"
ENV_VAR = "THREEDTK_DB"
PACKAGE_DATA = resources.files("threedtk").joinpath("data")

_RESOURCE_PATHS = ExitStack()
atexit.register(_RESOURCE_PATHS.close)

_CHUNK_SIZE = 1024 * 1024


class CatalogError(RuntimeError):
    """Raised when a catalogue cannot be located, fetched, or verified."""


class ChecksumMismatchError(CatalogError):
    """Raised when downloaded bytes do not match the expected SHA-256.

    Never recovered from by falling back to the received bytes: a catalogue
    that fails its checksum is discarded.
    """


@dataclass(frozen=True)
class CatalogRelease:
    """One immutable, citable release of the 3D'omics catalogue.

    Attributes:
        data_version: Calendar version (``YYYY.MM.DD``) Zenodo tracks.
        schema_version: Integer schema contract the code is written against.
        filename: Artefact file name inside the Zenodo record.
        sha256: Expected SHA-256 of the artefact.
        url: Direct download URL for the artefact.
        version_doi: DOI of this exact version. This is what the code pins.
        concept_doi: DOI that always resolves to the latest version. Cite this.
        license: SPDX-ish licence label of the data.
        size_bytes: Approximate artefact size, for progress and messaging.
    """

    data_version: str
    schema_version: int
    filename: str
    sha256: str
    url: str
    version_doi: str
    concept_doi: str
    license: str
    size_bytes: int


#: The catalogue release this ``3dtk`` is built and tested against.
#:
#: Mirrors ``database/catalog.json``. Bump this together with
#: ``SUPPORTED_SCHEMA_VERSIONS`` when adopting a new catalogue; see
#: ``RELEASING.md``.
PINNED_CATALOG = CatalogRelease(
    data_version="2026.08.29",
    schema_version=2,
    filename="3domics-2026.08.29.sqlite",
    sha256="2b779ef3f6303ac97242ee0165cea275924067767fe77c946a9b1c6da2c87120",
    url=(
        "https://zenodo.org/api/records/22159112/files/"
        "3domics-2026.08.29.sqlite/content"
    ),
    version_doi="10.5281/zenodo.22159112",
    concept_doi="10.5281/zenodo.22159111",
    license="CC-BY-4.0",
    size_bytes=61612032,
)

#: Zenodo concept record id, for ``scripts/sync_catalog.py`` version discovery.
CONCEPT_RECID = "22159111"


def cache_dir() -> Path:
    """Return the directory catalogues are cached in."""
    return Path(user_cache_dir(APP_NAME))


def cached_catalog_path(release: CatalogRelease = PINNED_CATALOG) -> Path:
    """Return the cache location for ``release``, whether or not it exists."""
    return cache_dir() / release.filename


def bundled_catalog_path() -> Path | None:
    """Return a bundled catalogue resource, or ``None`` when none was shipped.

    Bundling is off by default. When a ``.sqlite`` is present under
    ``threedtk/data/`` it becomes the last-resort source, so an offline-first
    build needs no code change -- only a packaging one.
    """
    try:
        if not PACKAGE_DATA.is_dir():
            return None
        candidates = sorted(
            entry for entry in PACKAGE_DATA.iterdir() if entry.name.endswith(".sqlite")
        )
    except (FileNotFoundError, NotADirectoryError):
        return None
    if not candidates:
        return None
    return _RESOURCE_PATHS.enter_context(resources.as_file(candidates[-1]))


def resolve_catalog_path(
    catalog_path: str | Path | None = None,
    *,
    auto_download: bool = True,
    release: CatalogRelease = PINNED_CATALOG,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Resolve which catalogue file to read.

    Args:
        catalog_path: An explicit path, which short-circuits every other step.
        auto_download: Whether a missing cached catalogue may be fetched.
            ``False`` makes the call offline-only and raises instead.
        release: The release to look for and, if permitted, download.
        progress: Optional callback receiving human-readable progress lines.

    Returns:
        An absolute path to a catalogue file. The file is guaranteed to exist
        only when it came from the cache, a download, or a bundled resource;
        an explicit path is returned as given so callers can report it.

    Raises:
        CatalogError: If no catalogue is available and none may be downloaded.
    """
    if catalog_path is not None:
        return Path(catalog_path).expanduser().resolve()

    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Path(from_env).expanduser().resolve()

    cached = cached_catalog_path(release)
    if cached.is_file():
        return cached.resolve()

    bundled = bundled_catalog_path()
    if bundled is not None:
        return Path(bundled).resolve()

    if not auto_download:
        raise CatalogError(
            f"No 3D'omics catalogue is available locally. Run `3dtk database sync` "
            f"to download release {release.data_version} "
            f"({_format_bytes(release.size_bytes)}) into {cache_dir()}, "
            f"or point --db / ${ENV_VAR} at an existing file."
        )

    return download_catalog(cached, release=release, progress=progress).resolve()


def download_catalog(
    destination: str | Path,
    *,
    release: CatalogRelease = PINNED_CATALOG,
    progress: Callable[[str], None] | None = None,
    overwrite: bool = False,
    fetch: Callable[[str], Iterable[bytes]] | None = None,
) -> Path:
    """Download ``release`` to ``destination``, verifying its SHA-256.

    The bytes are streamed to a ``.part`` sibling and only promoted to
    ``destination`` once the checksum matches, so a failed or interrupted
    download can never be mistaken for a usable catalogue.

    Args:
        destination: Final path for the catalogue file.
        release: The release to fetch.
        progress: Optional callback receiving human-readable progress lines.
        overwrite: Re-download even if ``destination`` already exists.
        fetch: Optional chunk iterator factory, for tests. Defaults to a
            streaming HTTP GET.

    Returns:
        The path the catalogue was written to.

    Raises:
        ChecksumMismatchError: If the downloaded bytes fail verification. The
            partial file is removed rather than used.
    """
    target = Path(destination).expanduser()
    if target.is_file() and not overwrite:
        _emit(progress, f"Catalogue already present at {target}.")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    chunks = (fetch or _http_chunks)(release.url)

    digest = hashlib.sha256()
    written = 0
    _emit(
        progress,
        f"Downloading 3D'omics catalogue {release.data_version} "
        f"({_format_bytes(release.size_bytes)}) from {release.version_doi}...",
    )
    try:
        with partial.open("wb") as handle:
            for chunk in chunks:
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
                written += len(chunk)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    actual = digest.hexdigest()
    if actual != release.sha256:
        partial.unlink(missing_ok=True)
        raise ChecksumMismatchError(
            f"Checksum mismatch for {release.filename}: expected "
            f"{release.sha256}, got {actual}. The download was discarded."
        )

    partial.replace(target)
    _emit(progress, f"Verified SHA-256 and cached {written:,} bytes at {target}.")
    return target


def file_sha256(path: str | Path) -> str:
    """Return the hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def catalog_source_label(path: Path, release: CatalogRelease = PINNED_CATALOG) -> str:
    """Describe where a resolved catalogue came from, for ``3dtk database``."""
    resolved = Path(path).resolve()
    from_env = os.environ.get(ENV_VAR)
    if from_env and Path(from_env).expanduser().resolve() == resolved:
        return f"environment ({ENV_VAR})"
    if resolved == cached_catalog_path(release).resolve():
        return "cache"
    bundled = bundled_catalog_path()
    if bundled is not None and Path(bundled).resolve() == resolved:
        return "bundled"
    return "custom"


def _http_chunks(url: str) -> Iterable[bytes]:
    import requests

    with requests.get(url, stream=True, timeout=(10, 300)) as response:
        response.raise_for_status()
        yield from response.iter_content(chunk_size=_CHUNK_SIZE)


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{size} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
