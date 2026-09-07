# Changelog

All notable changes to `3dtk` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project scaffolding: `pyproject.toml` publishing the `3dtk` distribution with
  the `threedtk` import package and a `3dtk` console script, GPLv3 licence.
- `threedtk.catalog`: the four-step catalogue resolver (`--db` → `THREEDTK_DB`
  → user cache → bundled resource), the pinned `CatalogRelease` for
  `2026.08.29` (version DOI `10.5281/zenodo.22159112`), and a checksum-verified
  downloader that discards bytes failing SHA-256 rather than using them.
- `threedtk.sources`: denormalised join SQL for all seven targets, carrying
  parent metadata down to child rows. Joins microsamples to their sequencing
  libraries across the ENA-accession bridge, since the two tables use different
  `microsample_id` namespaces and share no values.
- `threedtk.query`: the declarative `TargetConfig`/`TARGETS` engine, filter
  building, `--where` validation, column presets, `catalog_meta` reading, and
  `schema_version` validation against `SUPPORTED_SCHEMA_VERSIONS = {2}`.
- `threedtk.output`, `threedtk.values`, `threedtk.fields`, `threedtk.stats`:
  Rich table / CSV / TSV rendering, distinct-value counts, field listings, and
  declarative per-target summaries with top-N breakdowns.
- `threedtk.counts`: dense reconstruction of the sparse count matrices. Axes
  come from `matrix_axes` rather than `SELECT DISTINCT`, so an all-zero genome
  or sample keeps its place. Verified to reproduce all 82 original CSVs
  cell-for-cell, including row and column order. Matrices within an experiment
  share a genome axis and can be merged into one wide matrix, and a companion
  coordinate table aligned to the matrix columns makes the export directly
  usable for spatial analysis.
- `threedtk.terms`: data-usage gate with placeholder wording marked `TODO`
  rather than invented policy.
- `threedtk.ena`: ENA Portal API resolution of run accessions to FASTQ URLs,
  MD5s and sizes. Batches through `POST /search` with an `OR` query, because
  `filereport?accession=A,B,C` silently returns a header and no rows; 250
  accessions resolve in two requests.
- `threedtk.download`: chunked HTTP/FTP downloads with Rich progress, resumable
  skipping, streaming gzip CRC validation, and verification against the MD5 and
  byte size ENA publishes per file. `--script` emits a batch script that
  re-checks MD5s too.
- `threedtk.fetch`: resolves a filtered record set into download jobs, reporting
  records with no accession, accessions ENA does not know, and metabolomics
  macrosamples that point at MetaboLights, separately rather than dropping them.
- `threedtk.api`: `Database` context manager with seven typed collections, each
  supporting `query`, `count`, `values` and `stats`; `fetch` on macrosamples and
  microsamples; `matrices`, `export` and `coordinates` on counts.
- `threedtk.filters` + `threedtk.commands`: CLI filter specifications and the
  Typer app factory, so all seven targets share one action grammar by
  construction.
- `3dtk` CLI: root overview, `--version`, `--db`, per-target sub-apps, and
  `3dtk database` (`info`, `where`, `sync`).

- `tests/`: a pytest suite covering the query engine, catalogue resolution,
  dense counts export, ENA resolution, downloads, fetch planning, stats, values,
  manifest, terms, the Python API and the CLI. They build a miniature fixture
  catalogue in a temp directory and make no network calls, verified by running
  the suite with sockets blocked.

- `scripts/sync_catalog.py`: resolve a release under the Zenodo concept (latest
  or a pinned `--data-version`), verify it against its `.sha256` sidecar, check
  its `schema_version`, then `--download` it and/or `--pin` it by rewriting
  `PINNED_CATALOG`. Says explicitly when it resolved "latest" rather than a pin.

- Repository furniture: `README.md` (documenting the `pip install 3dtk` →
  `import threedtk` split prominently), `RELEASING.md` with the four version
  lines and the outstanding pre-release tasks, `CITATION.cff`, `.zenodo.json`,
  `codemeta.json`, GPLv3 `LICENSE`.
- `.github/workflows/ci.yml`: pytest on Python 3.10–3.14, `python -m build`, CLI
  smoke tests against real records, and a step that rebuilds every count matrix
  in the catalogue and checks it against `source_files.row_count`. The catalogue
  is cached by `data_version`, which is safe because the pin is immutable.
- `.github/workflows/release.yml`: PyPI publish via Trusted Publishing, gated on
  a check that the pinned DOI is a version DOI rather than the concept DOI.
- `docs/`: Sphinx + Read the Docs, one page per target plus installation,
  quickstart, database, identifiers, outputs, fetching, api and advanced.

### Fixed

- `query.resolve_catalog_path` now forwards `auto_download`, so
  `3dtk database where` stays offline instead of raising `TypeError`.
- The CLI's `fetch` now records unfetchable records in the manifest even when
  nothing is downloadable, matching the Python API. Previously a fetch that
  matched only MetaboLights macrosamples returned without accounting for them.

### Notes

- Specimen `treatment_group` holds unresolved Airtable record ids rather than
  readable labels, so column presets and stats breakdowns display `treatment`
  and `treatment_name` instead. `treatment_group` stays filterable. Resolving it
  is a `database-build` change.
