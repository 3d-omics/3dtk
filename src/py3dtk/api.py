"""Public Python API for the 3D'omics ToolKit.

This module defines everything exposed at the top level of the ``py3dtk``
package: the :class:`Database` entry point, one collection per level of the
3D'omics hierarchy, and the typed records they return.

Note the name split -- the distribution is ``3dtk`` but the import package is
``py3dtk``, because Python identifiers cannot begin with a digit::

    pip install 3dtk       # distribution
    import py3dtk        # package

Example:
    >>> import py3dtk
    >>> with py3dtk.Database() as db:
    ...     rows = db.microsamples.query(experiment_id="G", sex="female", limit=5)
    >>> rows[0].x_coord  # doctest: +SKIP
    13851.42

See the Sphinx documentation (``docs/api.rst``) for an extended guide.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from py3dtk.catalog import CatalogError, ChecksumMismatchError
from py3dtk.counts import (
    CountsError,
    DenseMatrix,
    MatrixSource,
    dense_matrix,
    list_matrix_sources,
    sample_coordinates,
)
from py3dtk.download import DownloadJob, DownloadResult, download_jobs, write_batch_script
from py3dtk.ena import EnaRun
from py3dtk.fetch import FetchPlan, UnfetchableRecord, plan_fetch
from py3dtk.manifest import ManifestEntry, append_manifest_entry
from py3dtk.query import (
    DEFAULT_QUERY_LIMIT,
    UnsupportedSchemaVersionError,
    count_rows,
    query_rows,
    read_catalog_meta,
    resolve_catalog_path,
    validate_catalog_schema,
)
from py3dtk.stats import StatBreakdown, TargetStats, target_stats
from py3dtk.values import DEFAULT_VALUES_LIMIT, value_rows


@dataclass(frozen=True, slots=True)
class Experiment:
    """A 3D'omics experiment: the top level of the hierarchy.

    Every field is optional because a query may request a subset of columns.
    """

    experiment_id: str | None = None
    experiment_name: str | None = None
    experiment_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    bioproject_accession: str | None = None
    bioproject_link: str | None = None
    mag_description: str | None = None
    mag_completeness_avg: float | None = None
    mag_contamination_avg: float | None = None
    mag_new_species_pct: float | None = None
    mag_count: int | None = None
    doi: str | None = None
    link: str | None = None
    has_genome_catalogue: int | None = None


@dataclass(frozen=True, slots=True)
class Specimen:
    """A sampled host animal, with its experiment context."""

    specimen_id: str | None = None
    experiment_id: str | None = None
    experiment_name: str | None = None
    experiment_type: str | None = None
    biosample_accession: str | None = None
    biosample_link: str | None = None
    pen: str | None = None
    slaughtering_date: str | None = None
    slaughtering_day_count: int | None = None
    treatment: str | None = None
    treatment_name: str | None = None
    treatment_group: str | None = None
    weight: float | None = None
    dpi: int | None = None
    sex: str | None = None
    species_scientific: str | None = None
    species_common: str | None = None
    taxid: str | None = None
    lifestage: str | None = None


@dataclass(frozen=True, slots=True)
class Macrosample:
    """A bulk sample taken from a specimen, with its sequencing library.

    ``library_id`` and ``run_accession`` come from ``macrosample_sequencing``,
    reached across the ENA-accession bridge; metabolomics macrosamples carry a
    ``metabolights_accession`` instead of an ENA accession.
    """

    macrosample_id: str | None = None
    code: str | None = None
    container: str | None = None
    data_type: str | None = None
    description: str | None = None
    preservative: str | None = None
    sample_type: str | None = None
    ena_accession: str | None = None
    ena_link: str | None = None
    metabolights_accession: str | None = None
    metabolights_link: str | None = None
    library_id: str | None = None
    run_accession: str | None = None
    experimental_unit: str | None = None
    specimen_id: str | None = None
    experiment_id: str | None = None
    experiment_name: str | None = None
    pen: str | None = None
    dpi: int | None = None
    treatment: str | None = None
    treatment_group: str | None = None
    specimen_weight: float | None = None
    sex: str | None = None
    species_scientific: str | None = None
    species_common: str | None = None
    taxid: str | None = None
    lifestage: str | None = None


@dataclass(frozen=True, slots=True)
class Cryosection:
    """A cryosection cut from a macrosample; the owner of a count matrix."""

    cryosection_id: str | None = None
    macrosample_id: str | None = None
    microsample_count: int | None = None
    position: str | None = None
    slide: str | None = None
    slide_date: str | None = None
    has_image: int | None = None
    sample_type: str | None = None
    data_type: str | None = None
    specimen_id: str | None = None
    experiment_id: str | None = None
    experiment_name: str | None = None
    treatment: str | None = None
    treatment_group: str | None = None
    sex: str | None = None
    species_scientific: str | None = None
    species_common: str | None = None
    taxid: str | None = None
    lifestage: str | None = None


@dataclass(frozen=True, slots=True)
class Microsample:
    """A laser-captured microsample: the spatial unit of 3D'omics.

    Carries two coordinate systems. ``x_coord``/``y_coord`` are the
    laser-microdissection stage coordinates recorded against the microsample
    itself; ``pixel_x``/``pixel_y`` are image coordinates recorded against the
    sequencing library. ``library_id`` is the sequencing-side identifier
    (``M300653``), which is a different namespace from ``microsample_id``
    (``G121eI102A003``) -- the two are matched on ENA accession.
    """

    microsample_id: str | None = None
    cryosection_id: str | None = None
    collection_method: str | None = None
    date: str | None = None
    lm_batch: str | None = None
    sample_type: str | None = None
    size: float | None = None
    x_coord: float | None = None
    y_coord: float | None = None
    ena_accession: str | None = None
    ena_link: str | None = None
    library_id: str | None = None
    run_accession: str | None = None
    shape: str | None = None
    pixel_x: int | None = None
    pixel_y: int | None = None
    macrosample_id: str | None = None
    cryosection_position: str | None = None
    slide: str | None = None
    slide_date: str | None = None
    specimen_id: str | None = None
    macrosample_type: str | None = None
    data_type: str | None = None
    experiment_id: str | None = None
    experiment_name: str | None = None
    pen: str | None = None
    dpi: int | None = None
    treatment: str | None = None
    treatment_group: str | None = None
    sex: str | None = None
    species_scientific: str | None = None
    species_common: str | None = None
    taxid: str | None = None
    lifestage: str | None = None


@dataclass(frozen=True, slots=True)
class Genome:
    """A genome from an experiment's catalogue.

    ``genome`` identifiers are ``<library>:<bin>`` and are scoped to an
    experiment's catalogue, *not* globally unique -- the key is
    ``(experiment_id, genome)``. Taxonomy is returned with GTDB rank prefixes
    stripped for display; filters accept either form.
    """

    genome: str | None = None
    experiment_id: str | None = None
    experiment_name: str | None = None
    source_id: str | None = None
    quality: str | None = None
    completeness: float | None = None
    contamination: float | None = None
    length: int | None = None
    domain: str | None = None
    phylum: str | None = None
    # ``class`` is a keyword, so the field is exposed as ``class_``.
    class_: str | None = None
    order: str | None = None
    family: str | None = None
    genus: str | None = None
    species: str | None = None


@dataclass(frozen=True, slots=True)
class CountCell:
    """One non-zero cell of a count matrix, with taxonomy and coordinates."""

    level: str | None = None
    experiment_id: str | None = None
    cryosection_id: str | None = None
    source_id: str | None = None
    genome: str | None = None
    sample: str | None = None
    count: float | None = None
    specimen_id: str | None = None
    macrosample_id: str | None = None
    sample_type: str | None = None
    x_coord: float | None = None
    y_coord: float | None = None
    pixel_x: int | None = None
    pixel_y: int | None = None
    domain: str | None = None
    phylum: str | None = None
    class_: str | None = None
    order: str | None = None
    family: str | None = None
    genus: str | None = None
    species: str | None = None
    completeness: float | None = None
    contamination: float | None = None


@dataclass(frozen=True, slots=True)
class ValueCount:
    """A distinct value and the number of records carrying it."""

    value: str
    count: int


@dataclass(frozen=True, slots=True)
class ValuesResult:
    """Distinct values of a field, with counts, after filters."""

    field: str
    rows: tuple[ValueCount, ...]


@dataclass(frozen=True, slots=True)
class FetchSummary:
    """Outcome of a :meth:`fetch` call.

    Attributes:
        plan: The resolved plan the fetch executed.
        results: Per-file download outcomes (empty in batch-script mode).
        batch_script: Path to the generated script, or ``None``.
        manifest_path: Path to the appended manifest, or ``None`` in batch mode.
    """

    plan: FetchPlan
    results: tuple[DownloadResult, ...] = ()
    batch_script: Path | None = None
    manifest_path: Path | None = None

    @property
    def target(self) -> str:
        return self.plan.target

    @property
    def matched_count(self) -> int:
        return self.plan.matched_count

    @property
    def queued_count(self) -> int:
        return len(self.plan.jobs)


#: Maps a dataclass field name to its catalogue column where they differ.
_FIELD_COLUMNS = {"class_": "class"}


class Database:
    """Python interface to the 3D'omics SQLite catalogue.

    Opens the catalogue resolved by :func:`py3dtk.catalog.resolve_catalog_path`
    -- an explicit ``path``, then ``PY3DTK_DB``, then the user cache
    (downloading the pinned release on first use), then a bundled resource --
    and exposes one collection per level:

    * :attr:`experiments`, :attr:`specimens`, :attr:`macrosamples`,
      :attr:`cryosections`, :attr:`microsamples`, :attr:`genomes`,
      :attr:`counts`

    Every collection supports ``query()``, ``values()``, ``stats()`` and
    ``count()``; :attr:`macrosamples` and :attr:`microsamples` add ``fetch()``;
    :attr:`counts` adds ``matrices()`` and ``export()``.

    Example:
        >>> import py3dtk
        >>> with py3dtk.Database() as db:
        ...     genomes = db.genomes.query(quality="high", genus="Faeciplasma")
        ...     matrix = db.counts.export(experiment_id="G", level="micro")

    Args:
        path: Path to a catalogue. ``None`` uses the standard resolution order.

    Raises:
        FileNotFoundError: If the resolved catalogue does not exist.
        UnsupportedSchemaVersionError: If its ``schema_version`` is unreadable
            by this release.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = resolve_catalog_path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Catalogue does not exist: {self.path}")
        validate_catalog_schema(self.path)
        self.experiments = ExperimentCollection(self)
        self.specimens = SpecimenCollection(self)
        self.macrosamples = MacrosampleCollection(self)
        self.cryosections = CryosectionCollection(self)
        self.microsamples = MicrosampleCollection(self)
        self.genomes = GenomeCollection(self)
        self.counts = CountsCollection(self)
        self._closed = False

    @property
    def meta(self) -> dict[str, str]:
        """The catalogue's ``catalog_meta`` identity map."""
        return read_catalog_meta(self.path)

    def __enter__(self) -> Database:
        self._ensure_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        """Mark the database closed so further queries raise."""
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("3dtk database is closed.")


class _Collection:
    """Shared behaviour for every level's collection."""

    target: str
    record_type: type

    def __init__(self, database: Database) -> None:
        self._database = database

    def query(
        self,
        *,
        where: str | None = None,
        limit: int | None = DEFAULT_QUERY_LIMIT,
        columns: str | Sequence[str] | None = None,
        **filters: Any,
    ) -> list[Any]:
        """Query records.

        Args:
            where: Optional validated SQL predicate fragment.
            limit: Maximum records to return; ``None`` for no limit.
            columns: A preset name, ``"all"``, a comma-separated string, or a
                sequence of column names.
            **filters: Field filters using CLI option names with underscores.
                Sequences are treated like comma-separated CLI values.

        Returns:
            Typed records for this collection.
        """
        self._database._ensure_open()
        rows = query_rows(
            self._database.path,
            self.target,
            filters=_normalize_filters(filters),
            where=where,
            limit=limit,
            columns=_column_spec(columns),
        )
        return [_record_from_row(self.record_type, row) for row in rows]

    def count(self, *, where: str | None = None, **filters: Any) -> int:
        """Count matching records, ignoring any limit."""
        self._database._ensure_open()
        return count_rows(
            self._database.path,
            self.target,
            filters=_normalize_filters(filters),
            where=where,
        )

    def values(
        self,
        field: str,
        *,
        where: str | None = None,
        limit: int = DEFAULT_VALUES_LIMIT,
        **filters: Any,
    ) -> ValuesResult:
        """Count distinct values of ``field`` after applying filters."""
        self._database._ensure_open()
        resolved_field, rows = value_rows(
            str(self._database.path),
            target=self.target,
            field=field,
            filters=_normalize_filters(filters),
            where=where,
            limit=limit,
        )
        return ValuesResult(
            field=resolved_field,
            rows=tuple(ValueCount(value=r["value"], count=r["count"]) for r in rows),
        )

    def stats(self, *, where: str | None = None, **filters: Any) -> TargetStats:
        """Summarise matching records with headline figures and breakdowns."""
        self._database._ensure_open()
        return target_stats(
            catalog_path=str(self._database.path),
            target=self.target,
            filters=_normalize_filters(filters),
            where=where,
        )


class _FetchableCollection(_Collection):
    """A collection whose records resolve to downloadable ENA files."""

    def fetch(
        self,
        *,
        output_dir: str | Path = Path("downloads"),
        batch: str | Path | None = None,
        manifest_path: str | Path = Path("manifest.jsonl"),
        overwrite: bool = False,
        protocol: str = "https",
        where: str | None = None,
        limit: int | None = None,
        **filters: Any,
    ) -> FetchSummary:
        """Download matching records' files, or script the downloads.

        Accessions are resolved through the ENA Portal API in batches before
        anything is downloaded, and each file is verified against the MD5 ENA
        publishes for it.

        Args:
            output_dir: Files land in ``<output_dir>/<target>/<record_id>/``.
            batch: Write a shell script here instead of downloading now.
            manifest_path: Append-only JSONL log of every file.
            overwrite: Overwrite existing files instead of skipping.
            protocol: ``"https"`` (default) or ``"ftp"``.
            where: Optional validated SQL predicate fragment.
            limit: Maximum records to fetch.
            **filters: Field filters, as for :meth:`query`.

        Returns:
            A :class:`FetchSummary`.
        """
        self._database._ensure_open()
        plan = plan_fetch(
            self._database.path,
            self.target,
            filters=_normalize_filters(filters),
            where=where,
            limit=limit,
            output_dir=output_dir,
            protocol=protocol,
        )
        jobs = list(plan.jobs)

        if batch is not None:
            return FetchSummary(
                plan=plan, batch_script=write_batch_script(batch, jobs, overwrite=overwrite)
            )

        manifest = Path(manifest_path)
        for record in plan.unfetchable:
            append_manifest_entry(
                manifest,
                ManifestEntry(
                    entry_type=self.target.rstrip("s"),
                    id_field=f"{self.target.rstrip('s')}_id",
                    id_value=record.record_id,
                    url=None,
                    path=None,
                    checksum=None,
                    status=record.reason,
                ),
            )
        results = download_jobs(jobs, manifest_path=manifest, overwrite=overwrite)
        return FetchSummary(
            plan=plan, results=tuple(results), manifest_path=manifest
        )


class ExperimentCollection(_Collection):
    """Experiments, via ``Database.experiments``."""

    target = "experiments"
    record_type = Experiment


class SpecimenCollection(_Collection):
    """Specimens, via ``Database.specimens``."""

    target = "specimens"
    record_type = Specimen


class MacrosampleCollection(_FetchableCollection):
    """Macrosamples, via ``Database.macrosamples``."""

    target = "macrosamples"
    record_type = Macrosample


class CryosectionCollection(_Collection):
    """Cryosections, via ``Database.cryosections``."""

    target = "cryosections"
    record_type = Cryosection


class MicrosampleCollection(_FetchableCollection):
    """Microsamples, via ``Database.microsamples``."""

    target = "microsamples"
    record_type = Microsample


class GenomeCollection(_Collection):
    """Genomes, via ``Database.genomes``."""

    target = "genomes"
    record_type = Genome


class CountsCollection(_Collection):
    """Count cells and dense matrices, via ``Database.counts``."""

    target = "counts"
    record_type = CountCell

    def matrices(
        self,
        *,
        level: str | None = None,
        experiment_id: str | None = None,
        cryosection_id: str | None = None,
        source_id: str | None = None,
    ) -> list[MatrixSource]:
        """List the count matrices matching the given selectors."""
        self._database._ensure_open()
        return list_matrix_sources(
            self._database.path,
            level=level,
            experiment_id=experiment_id,
            cryosection_id=cryosection_id,
            source_id=source_id,
        )

    def export(
        self,
        *,
        level: str | None = None,
        experiment_id: str | None = None,
        cryosection_id: str | None = None,
        source_id: str | None = None,
        genomes: Sequence[str] | None = None,
        samples: Sequence[str] | None = None,
        verify: bool = True,
        **taxonomy: Any,
    ) -> DenseMatrix:
        """Rebuild a dense genome x sample matrix, restoring dropped zeros.

        Matrices are selected the same way :meth:`matrices` selects them; when
        several match they are merged by unioning the genome axis and
        concatenating sample columns, which is well-defined because matrices
        within an experiment share a genome axis.

        Args:
            level: ``"macro"`` or ``"micro"``.
            experiment_id: Restrict to one experiment.
            cryosection_id: Restrict to one cryosection.
            source_id: Select one matrix exactly.
            genomes: Restrict rows to these genome identifiers.
            samples: Restrict columns to these sample identifiers.
            verify: Check the rebuilt matrix against ``source_files.row_count``.
                Skipped automatically when the export is filtered.
            **taxonomy: GTDB rank filters, e.g. ``genus="Faeciplasma"``.

        Returns:
            A :class:`~py3dtk.counts.DenseMatrix` whose axis order follows
            ``matrix_axes``.
        """
        self._database._ensure_open()
        sources = self.matrices(
            level=level,
            experiment_id=experiment_id,
            cryosection_id=cryosection_id,
            source_id=source_id,
        )
        matrix = dense_matrix(
            self._database.path,
            sources,
            genomes=genomes,
            samples=samples,
            taxonomy=taxonomy or None,
        )
        if verify:
            matrix.verify()
        return matrix

    def coordinates(self, matrix: DenseMatrix) -> list[dict[str, Any]]:
        """Return the coordinate companion table for a matrix's columns."""
        self._database._ensure_open()
        level = matrix.sources[0].level if matrix.sources else "micro"
        return sample_coordinates(self._database.path, matrix.samples, level=level)


def _column_spec(columns: str | Sequence[str] | None) -> str | None:
    if columns is None or isinstance(columns, str):
        return columns
    return ",".join(columns)


def _normalize_filters(filters: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in filters.items():
        if value is None or isinstance(value, bool):
            normalized[key] = value
        elif isinstance(value, str) or key.endswith(("_min", "_max")):
            normalized[key] = value
        elif isinstance(value, Sequence):
            normalized[key] = ",".join(str(item) for item in value)
        else:
            normalized[key] = str(value)
    return normalized


def _record_from_row(record_type: type, row: Any) -> Any:
    keys = set(row.keys())
    payload: dict[str, Any] = {}
    for name in record_type.__dataclass_fields__:
        column = _FIELD_COLUMNS.get(name, name)
        payload[name] = row[column] if column in keys else None
    return record_type(**payload)


__all__ = [
    "CatalogError",
    "ChecksumMismatchError",
    "CountCell",
    "CountsError",
    "Cryosection",
    "Database",
    "DenseMatrix",
    "DownloadJob",
    "DownloadResult",
    "EnaRun",
    "Experiment",
    "FetchPlan",
    "FetchSummary",
    "Genome",
    "Macrosample",
    "MatrixSource",
    "Microsample",
    "Specimen",
    "StatBreakdown",
    "TargetStats",
    "UnfetchableRecord",
    "UnsupportedSchemaVersionError",
    "ValueCount",
    "ValuesResult",
]
