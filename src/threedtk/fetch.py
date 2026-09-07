"""Turn a filtered record set into verified downloads.

``ehitk`` reads ready-made ``url1``/``url2`` columns from its catalogue. The
3D'omics catalogue stores only browser links and run accessions, so fetching is
a two-stage operation: query the records, then resolve their accessions through
the ENA Portal API in batches (see :mod:`threedtk.ena`) before any bytes move.

Records that cannot produce a download are never silently dropped. A record with
no accession, an accession ENA does not recognise, and a metabolomics
macrosample that points at MetaboLights instead are each reported separately, so
the caller can tell "nothing matched" from "matched but unfetchable".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from threedtk.download import DownloadJob, destination_for_url
from threedtk.ena import DEFAULT_PROTOCOL, EnaRun, resolve_runs
from threedtk.query import QueryValidationError, query_rows

#: Per-target: the record id column, the accession column, and a manifest label.
FETCHABLE_TARGETS: dict[str, dict[str, str]] = {
    "microsamples": {
        "id_column": "microsample_id",
        "accession_column": "run_accession",
        "fallback_accession_column": "ena_accession",
        "entry_type": "microsample",
    },
    "macrosamples": {
        "id_column": "macrosample_id",
        "accession_column": "run_accession",
        "fallback_accession_column": "ena_accession",
        "entry_type": "macrosample",
    },
}


@dataclass(frozen=True)
class UnfetchableRecord:
    """A matched record that produced no download job, and why."""

    record_id: str
    reason: str
    detail: str | None = None


@dataclass(frozen=True)
class FetchPlan:
    """What a fetch would do, resolved but not yet executed.

    Attributes:
        target: The target that was queried.
        matched_count: Records matching the filters.
        jobs: Download jobs, two per paired-end run.
        unfetchable: Matched records that yielded no job, with reasons.
        runs: The ENA resolutions used, keyed by accession.
    """

    target: str
    matched_count: int
    jobs: tuple[DownloadJob, ...]
    unfetchable: tuple[UnfetchableRecord, ...] = ()
    runs: Mapping[str, EnaRun] = field(default_factory=dict)

    @property
    def total_bytes(self) -> int:
        """Total size of the queued files where ENA published one."""
        return sum(job.expected_size or 0 for job in self.jobs)

    def reasons(self) -> dict[str, int]:
        """Count unfetchable records by reason, for a one-line summary."""
        counts: dict[str, int] = {}
        for record in self.unfetchable:
            counts[record.reason] = counts.get(record.reason, 0) + 1
        return counts


def plan_fetch(
    catalog_path: str | Path,
    target: str,
    *,
    filters: Mapping[str, Any] | None = None,
    where: str | None = None,
    limit: int | None = None,
    output_dir: str | Path = Path("downloads"),
    protocol: str = DEFAULT_PROTOCOL,
    ena_cache: dict[str, EnaRun] | None = None,
    resolver: Callable[..., dict[str, EnaRun]] | None = None,
    progress: Callable[[str], None] | None = None,
) -> FetchPlan:
    """Resolve matching records into download jobs without downloading.

    Args:
        catalog_path: Catalogue to query.
        target: ``"microsamples"`` or ``"macrosamples"``.
        filters: Field filters, as for a query.
        where: Optional validated SQL predicate.
        limit: Maximum records to consider.
        output_dir: Base directory; files land in
            ``<output_dir>/<target>/<record_id>/``.
        protocol: ``"https"`` (default) or ``"ftp"``.
        ena_cache: Optional accession cache reused across calls.
        resolver: Optional replacement for :func:`threedtk.ena.resolve_runs`.
        progress: Optional callback receiving progress lines.

    Returns:
        A :class:`FetchPlan`.
    """
    if target not in FETCHABLE_TARGETS:
        raise QueryValidationError(
            f"Target {target} has no downloadable files. "
            f"Fetchable targets: {', '.join(sorted(FETCHABLE_TARGETS))}."
        )
    spec = FETCHABLE_TARGETS[target]
    rows = query_rows(
        catalog_path, target, filters=filters, where=where, limit=limit, fetch=True
    )
    if not rows:
        return FetchPlan(target=target, matched_count=0, jobs=())

    accessions: list[str] = []
    prepared: list[tuple[str, str]] = []
    unfetchable: list[UnfetchableRecord] = []

    for row in rows:
        record_id = row[spec["id_column"]]
        keys = row.keys()
        accession = _first_value(
            row, keys, spec["accession_column"], spec["fallback_accession_column"]
        )
        if not accession:
            metabolights = (
                row["metabolights_accession"]
                if "metabolights_accession" in keys
                else None
            )
            if metabolights:
                unfetchable.append(
                    UnfetchableRecord(
                        record_id=record_id,
                        reason="metabolights",
                        detail=metabolights,
                    )
                )
            else:
                unfetchable.append(
                    UnfetchableRecord(record_id=record_id, reason="no_accession")
                )
            continue
        accessions.append(accession)
        prepared.append((record_id, accession))

    resolve = resolver or resolve_runs
    runs = (
        resolve(accessions, protocol=protocol, cache=ena_cache, progress=progress)
        if accessions
        else {}
    )

    jobs: list[DownloadJob] = []
    for record_id, accession in prepared:
        run = runs.get(accession)
        if run is None or not run.files:
            unfetchable.append(
                UnfetchableRecord(
                    record_id=record_id, reason="unresolved_accession", detail=accession
                )
            )
            continue
        base_directory = Path(output_dir) / target / str(record_id)
        for position, ena_file in enumerate(run.files, start=1):
            jobs.append(
                DownloadJob(
                    entry_type=spec["entry_type"],
                    id_field=spec["id_column"],
                    id_value=str(record_id),
                    url=ena_file.url,
                    destination=destination_for_url(
                        base_directory,
                        ena_file.url,
                        fallback_name=f"{record_id}_{position}.fastq.gz",
                    ),
                    md5=ena_file.md5,
                    expected_size=ena_file.size,
                )
            )

    return FetchPlan(
        target=target,
        matched_count=len(rows),
        jobs=tuple(jobs),
        unfetchable=tuple(unfetchable),
        runs=runs,
    )


def _first_value(row: Any, keys: Any, *columns: str) -> str | None:
    for column in columns:
        if column in keys:
            value = row[column]
            if value:
                return str(value).strip()
    return None


def format_bytes(size: int) -> str:
    """Render a byte count for progress messages."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{size} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
