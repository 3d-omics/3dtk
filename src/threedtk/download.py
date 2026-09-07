"""Chunked HTTP/FTP downloads with progress, integrity checks, and manifests.

Ported from ``ehitk``'s downloader, with one addition: ENA publishes an MD5 per
FASTQ file, so a downloaded file is checked against that as well as against the
streaming gzip CRC. The two checks catch different failures -- the MD5 proves
the bytes are the ones ENA published, the gzip check catches a truncated or
corrupted stream even when no MD5 is available.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shlex
from typing import Iterable
from urllib.parse import urlparse
import urllib.request
import zlib

import requests
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from threedtk.manifest import ManifestEntry, append_manifest_entry

CHUNK_SIZE = 1024 * 1024


class IntegrityError(Exception):
    """Raised when a downloaded file fails an integrity check."""


@dataclass(frozen=True)
class DownloadJob:
    """One file to download.

    Attributes:
        entry_type: Record type, for the manifest (e.g. ``"microsample"``).
        id_field: Name of the identifier column, for the manifest.
        id_value: The record identifier this file belongs to.
        url: Download URL.
        destination: Where the file is written.
        md5: Expected MD5, when the source publishes one.
        expected_size: Expected size in bytes, when published.
    """

    entry_type: str
    id_field: str
    id_value: str
    url: str
    destination: Path
    md5: str | None = None
    expected_size: int | None = None


@dataclass(frozen=True)
class DownloadResult:
    job: DownloadJob
    status: str
    checksum: str | None = None
    size: int | None = None
    error: str | None = None


class _GzipChecker:
    """Validate a gzip stream incrementally as chunks arrive.

    Feeding every chunk through a streaming decompressor verifies the gzip
    header, the per-member CRC32, and the uncompressed length in the trailer
    without buffering the file or making a second pass. Concatenated
    (multi-member) gzip files, such as bgzip output, are handled by restarting
    on the trailing bytes after each member ends.
    """

    def __init__(self) -> None:
        self._decompressor: zlib._Decompress | None = None
        self._in_member = False
        self._started = False

    def update(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._started = True
        data = chunk
        while data:
            if self._decompressor is None:
                self._decompressor = zlib.decompressobj(wbits=31)
            try:
                self._decompressor.decompress(data, CHUNK_SIZE)
            except zlib.error as exc:
                raise IntegrityError(f"gzip integrity check failed: {exc}") from exc
            self._in_member = True
            if self._decompressor.eof:
                data = self._decompressor.unused_data
                self._decompressor = None
                self._in_member = False
            elif self._decompressor.unconsumed_tail:
                data = self._decompressor.unconsumed_tail
            else:
                data = b""

    def finish(self) -> None:
        if not self._started:
            raise IntegrityError("downloaded file is empty")
        if self._in_member:
            raise IntegrityError("gzip stream is incomplete (truncated download)")


def filename_from_url(url: str, *, fallback: str) -> str:
    filename = Path(urlparse(url).path).name
    return filename or fallback


def destination_for_url(base_directory: Path, url: str, *, fallback_name: str) -> Path:
    return base_directory / filename_from_url(url, fallback=fallback_name)


def download_jobs(
    jobs: list[DownloadJob],
    *,
    manifest_path: str | Path,
    overwrite: bool = False,
    console: Console | None = None,
) -> list[DownloadResult]:
    """Download every job, appending one manifest entry per file."""
    if not jobs:
        return []

    active_console = console or Console()
    results: list[DownloadResult] = []

    with Progress(
        TextColumn("{task.fields[filename]}", justify="left"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=active_console,
    ) as progress:
        for job in jobs:
            result = _download_job(job, progress=progress, overwrite=overwrite)
            append_manifest_entry(
                manifest_path,
                ManifestEntry(
                    entry_type=job.entry_type,
                    id_field=job.id_field,
                    id_value=job.id_value,
                    url=job.url,
                    path=str(job.destination),
                    checksum=result.checksum,
                    size=result.size,
                    status=result.status,
                ),
            )
            results.append(result)

            if result.error:
                label = "Corrupt" if result.status == "corrupt" else "Failed"
                active_console.print(
                    f"[red]{label}[/red] {job.destination.name}: {result.error}"
                )

    return results


def write_batch_script(
    script_path: str | Path,
    jobs: list[DownloadJob],
    *,
    overwrite: bool = False,
) -> Path:
    """Write a self-contained shell script that downloads and verifies the jobs.

    The script re-checks each file's MD5 where ENA published one, so a batch run
    on a cluster gets the same integrity guarantee as a direct download.
    """
    path = Path(script_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Generated by 3dtk.",
        "",
        "md5_of() {",
        '  if command -v md5sum >/dev/null 2>&1; then md5sum "$1" | cut -d" " -f1;',
        '  else md5 -q "$1"; fi',
        "}",
        "",
    ]

    seen_directories: set[Path] = set()
    for job in jobs:
        if job.destination.parent not in seen_directories:
            seen_directories.add(job.destination.parent)
            lines.append(f"mkdir -p {shlex.quote(str(job.destination.parent))}")
    if seen_directories:
        lines.append("")

    for job in jobs:
        destination = shlex.quote(str(job.destination))
        url = shlex.quote(job.url)
        downloading = shlex.quote(f"Downloading {job.destination.name}")
        body = [
            f"echo {downloading}",
            f"curl --fail --location --output {destination} {url}",
        ]
        if job.md5:
            expected = shlex.quote(job.md5)
            body.extend(
                [
                    f'actual=$(md5_of {destination})',
                    f'if [ "$actual" != {expected} ]; then',
                    f"  echo {shlex.quote(f'MD5 mismatch for {job.destination.name}')} >&2",
                    f"  rm -f {destination}",
                    "  exit 1",
                    "fi",
                ]
            )
        if overwrite:
            lines.extend(body)
        else:
            skipping = shlex.quote(f"Skipping existing {job.destination.name}")
            lines.append(f"if [ -f {destination} ]; then")
            lines.append(f"  echo {skipping}")
            lines.append("else")
            lines.extend(f"  {statement}" for statement in body)
            lines.append("fi")
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _download_job(
    job: DownloadJob,
    *,
    progress: Progress,
    overwrite: bool,
) -> DownloadResult:
    destination = job.destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = Path(f"{destination}.part")

    if destination.exists() and not overwrite:
        return DownloadResult(job=job, status="skipped_existing")

    if temporary_path.exists():
        temporary_path.unlink()

    expect_gzip = destination.name.endswith(".gz")
    try:
        scheme = urlparse(job.url).scheme.lower()
        if scheme in {"http", "https"}:
            checksum, size = _download_http(
                job, temporary_path, progress, expect_gzip=expect_gzip
            )
        elif scheme == "ftp":
            checksum, size = _download_ftp(
                job, temporary_path, progress, expect_gzip=expect_gzip
            )
        else:
            raise ValueError(f"Unsupported URL scheme: {scheme}")

        temporary_path.replace(destination)
        return DownloadResult(job=job, status="downloaded", checksum=checksum, size=size)
    except IntegrityError as exc:
        # Keep the partial file for inspection rather than promoting it to the
        # final name, so a failed download is visible and easy to re-fetch.
        return DownloadResult(job=job, status="corrupt", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        if temporary_path.exists():
            temporary_path.unlink()
        return DownloadResult(job=job, status="failed", error=str(exc))


def _download_http(
    job: DownloadJob,
    temporary_path: Path,
    progress: Progress,
    *,
    expect_gzip: bool,
) -> tuple[str, int]:
    with requests.get(job.url, stream=True, timeout=(10, 300)) as response:
        response.raise_for_status()
        total_size = _parse_total_size(response.headers.get("content-length"))
        chunks = response.iter_content(chunk_size=CHUNK_SIZE)
        return _stream_to_disk(
            job, chunks, total_size, temporary_path, progress, expect_gzip=expect_gzip
        )


def _download_ftp(
    job: DownloadJob,
    temporary_path: Path,
    progress: Progress,
    *,
    expect_gzip: bool,
) -> tuple[str, int]:
    with urllib.request.urlopen(job.url, timeout=300) as response:
        total_size = _parse_total_size(getattr(response, "length", None))
        chunks = iter(lambda: response.read(CHUNK_SIZE), b"")
        return _stream_to_disk(
            job, chunks, total_size, temporary_path, progress, expect_gzip=expect_gzip
        )


def _stream_to_disk(
    job: DownloadJob,
    chunks: Iterable[bytes],
    total_size: int | None,
    temporary_path: Path,
    progress: Progress,
    *,
    expect_gzip: bool,
) -> tuple[str, int]:
    checksum = hashlib.sha256()
    md5 = hashlib.md5() if job.md5 else None
    gzip_checker = _GzipChecker() if expect_gzip else None
    bytes_written = 0
    expected_total = total_size if total_size is not None else job.expected_size
    task_id = progress.add_task(
        "download", filename=job.destination.name, total=expected_total
    )

    try:
        with temporary_path.open("wb") as handle:
            for chunk in chunks:
                if not chunk:
                    continue
                handle.write(chunk)
                checksum.update(chunk)
                if md5 is not None:
                    md5.update(chunk)
                if gzip_checker is not None:
                    gzip_checker.update(chunk)
                bytes_written += len(chunk)
                progress.update(task_id, advance=len(chunk))
    finally:
        progress.remove_task(task_id)

    if total_size is not None and bytes_written != total_size:
        raise IntegrityError(
            f"size mismatch: server reported {total_size} bytes but {bytes_written} "
            "were received (truncated download)"
        )
    if job.expected_size is not None and bytes_written != job.expected_size:
        raise IntegrityError(
            f"size mismatch: ENA lists {job.expected_size} bytes but "
            f"{bytes_written} were received"
        )
    if md5 is not None:
        actual_md5 = md5.hexdigest()
        if actual_md5.lower() != job.md5.lower():
            raise IntegrityError(
                f"MD5 mismatch: ENA published {job.md5}, got {actual_md5}"
            )
    if gzip_checker is not None:
        gzip_checker.finish()

    return checksum.hexdigest(), bytes_written


def _parse_total_size(raw_value: object) -> int | None:
    if raw_value in (None, "", -1):
        return None
    try:
        size = int(raw_value)
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None
