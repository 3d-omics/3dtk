"""Resolve ENA run accessions to downloadable FASTQ files.

The catalogue stores browser links (``https://www.ebi.ac.uk/ena/browser/view/
ERR15114245``) and run accessions, not file URLs, so ``fetch`` resolves them
through the ENA Portal API at request time.

Two things about that API shaped this module:

**Batch through ``/search``, not ``/filereport``.** ``filereport`` takes a single
``accession``; passing a comma-separated list returns a header row and *no
data*, silently. The ``/search`` endpoint with an ``OR`` query batches properly,
so a 500-microsample fetch issues a handful of requests rather than 500.

**ENA publishes an MD5 per file.** That is better provenance than a streaming
gzip CRC alone, so downloads verify the MD5 as well.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Mapping, Sequence

PORTAL_SEARCH_URL = "https://www.ebi.ac.uk/ena/portal/api/search"
PORTAL_FILEREPORT_URL = "https://www.ebi.ac.uk/ena/portal/api/filereport"

FIELDS = (
    "run_accession",
    "experiment_accession",
    "sample_accession",
    "fastq_ftp",
    "fastq_md5",
    "fastq_bytes",
    "submitted_ftp",
)

#: Accessions per Portal API request. 200 is verified working; the limit is the
#: length of the generated ``OR`` query, not a documented API cap.
DEFAULT_BATCH_SIZE = 200

#: ENA returns paths without a scheme (``ftp.sra.ebi.ac.uk/vol1/...``). HTTPS is
#: preferred: it supports range requests and traverses firewalls that block FTP.
DEFAULT_PROTOCOL = "https"


class EnaError(RuntimeError):
    """Raised when the ENA Portal API cannot be queried or parsed."""


@dataclass(frozen=True)
class EnaFile:
    """One downloadable file published for a run.

    Attributes:
        url: Fully-qualified download URL.
        md5: MD5 checksum ENA publishes for the file, if any.
        size: File size in bytes, if published.
    """

    url: str
    md5: str | None = None
    size: int | None = None

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class EnaRun:
    """The files and identifiers ENA publishes for one run accession."""

    run_accession: str
    files: tuple[EnaFile, ...]
    experiment_accession: str | None = None
    sample_accession: str | None = None


def run_browser_url(accession: str) -> str:
    """Return the ENA browser URL for an accession, as stored in the catalogue."""
    return f"https://www.ebi.ac.uk/ena/browser/view/{accession}"


def resolve_runs(
    accessions: Sequence[str],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    protocol: str = DEFAULT_PROTOCOL,
    fetch: Callable[[str, Mapping[str, str]], str] | None = None,
    cache: dict[str, EnaRun] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, EnaRun]:
    """Resolve run accessions to their published files.

    Args:
        accessions: Run accessions to resolve. Duplicates and blanks are
            ignored; order is not significant.
        batch_size: Accessions per API request.
        protocol: URL scheme to build, ``"https"`` (default) or ``"ftp"``.
        fetch: Optional ``(url, form_data) -> response_text`` callable, for
            tests. Defaults to a POST via ``requests``.
        cache: Optional mapping reused across calls so repeated accessions are
            not re-requested.
        progress: Optional callback receiving human-readable progress lines.

    Returns:
        A mapping of run accession to :class:`EnaRun`. Accessions ENA does not
        know about are absent from the mapping rather than raising.
    """
    if protocol not in {"https", "ftp"}:
        raise EnaError(f"Unsupported protocol: {protocol}. Use 'https' or 'ftp'.")

    resolved: dict[str, EnaRun] = {}
    pending: list[str] = []
    seen: set[str] = set()
    for accession in accessions:
        key = str(accession or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        if cache is not None and key in cache:
            resolved[key] = cache[key]
        else:
            pending.append(key)

    if not pending:
        return resolved

    request = fetch or _post_form
    batches = list(_chunked(pending, batch_size))
    for index, batch in enumerate(batches, start=1):
        if progress is not None:
            progress(
                f"Resolving {len(batch)} ENA accession(s) "
                f"[batch {index}/{len(batches)}]..."
            )
        text = request(
            PORTAL_SEARCH_URL,
            {
                "result": "read_run",
                "query": " OR ".join(f'run_accession="{a}"' for a in batch),
                "fields": ",".join(FIELDS),
                "format": "tsv",
                "limit": "0",
            },
        )
        for run in parse_filereport(text, protocol=protocol):
            resolved[run.run_accession] = run
            if cache is not None:
                cache[run.run_accession] = run

    return resolved


def parse_filereport(text: str, *, protocol: str = DEFAULT_PROTOCOL) -> list[EnaRun]:
    """Parse a Portal API TSV response into :class:`EnaRun` records.

    Paired-end runs list their files semicolon-separated across the
    ``fastq_ftp``, ``fastq_md5`` and ``fastq_bytes`` columns; the three lists are
    positionally aligned.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    header = lines[0].split("\t")
    try:
        index = {name: header.index(name) for name in ("run_accession", "fastq_ftp")}
    except ValueError as exc:
        raise EnaError(
            f"Unexpected ENA response header: {lines[0]!r}"
        ) from exc
    optional = {
        name: header.index(name) for name in header if name not in index
    }

    runs: list[EnaRun] = []
    for line in lines[1:]:
        cells = line.split("\t")

        def value(name: str) -> str:
            position = index.get(name, optional.get(name))
            if position is None or position >= len(cells):
                return ""
            return cells[position].strip()

        accession = value("run_accession")
        if not accession:
            continue

        paths = _split_list(value("fastq_ftp"))
        md5s = _split_list(value("fastq_md5"))
        sizes = _split_list(value("fastq_bytes"))
        files = tuple(
            EnaFile(
                url=_qualify(path, protocol),
                md5=md5s[position] if position < len(md5s) else None,
                size=_as_int(sizes[position]) if position < len(sizes) else None,
            )
            for position, path in enumerate(paths)
        )
        runs.append(
            EnaRun(
                run_accession=accession,
                files=files,
                experiment_accession=value("experiment_accession") or None,
                sample_accession=value("sample_accession") or None,
            )
        )
    return runs


def _split_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(";") if part.strip()]


def _qualify(path: str, protocol: str) -> str:
    if path.startswith(("http://", "https://", "ftp://")):
        return path
    return f"{protocol}://{path}"


def _as_int(raw: str) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _chunked(values: Sequence[str], size: int) -> Iterator[list[str]]:
    if size <= 0:
        raise EnaError("ENA batch size must be greater than zero.")
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def _post_form(url: str, data: Mapping[str, str]) -> str:
    import requests

    response = requests.post(url, data=dict(data), timeout=(10, 120))
    response.raise_for_status()
    return response.text
