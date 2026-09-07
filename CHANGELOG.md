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
