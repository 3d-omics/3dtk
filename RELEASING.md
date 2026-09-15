# Releasing 3dtk

The cross-repo runbook for shipping `3dtk`. It spans two repositories:

- **`3dtk`** (this repo) — the *consumer*: the Python CLI and API published to
  PyPI. It ships **no** catalogue; it pins one Zenodo version record.
- **[`3d-omics/database-build`](https://github.com/3d-omics/database-build)** —
  the *producer*: builds `3domics-<data_version>.sqlite` from Airtable and
  deposits it to Zenodo. See its own `RELEASING.md` for producer-side steps.

## Version lines

Four independent-but-linked version lines. Keep them distinct:

| Version line | Format | Lives in | Bumps when |
| --- | --- | --- | --- |
| `database-build` semver | `X.Y.Z` | `database-build` `pyproject.toml` | the generator code changes |
| `data_version` | `YYYY.MM.DD` (calendar) | the catalogue's `catalog_meta` table | the catalogue is regenerated from Airtable; **this is what Zenodo tracks** |
| `3dtk` semver | `X.Y.Z` | this repo's `pyproject.toml` | the consumer CLI/API changes |
| `schema_version` | integer | the catalogue's `catalog_meta` table | the catalogue schema changes in a way that breaks the code contract |

Every built catalogue records `data_version`, `schema_version`,
`built_with_3domics_db_build` and `source_snapshot` in `catalog_meta`, so a
loose `.sqlite` is self-identifying. `3dtk` validates `schema_version` when
opening a catalogue, and `3dtk database info` reports the whole identity.

The current contract: `schema_version` **2**, pinned `data_version`
**2026.08.29**, version DOI **10.5281/zenodo.22159112**.

## Two DOIs, two different jobs

- The **concept DOI** (`10.5281/zenodo.22159111`) always resolves to the latest
  version. **Cite this.** Never pin it.
- The **version DOI** (`10.5281/zenodo.22159112`) names one immutable record.
  **This is what the code pins**, together with the artefact's SHA-256.

`release.yml` refuses to publish if `PINNED_CATALOG.version_doi` equals the
concept DOI, if the SHA-256 is not 64 characters, or if the pinned
`schema_version` is outside `SUPPORTED_SCHEMA_VERSIONS`.

## Prerequisites

- Clones of `3dtk` and `database-build`.
- Release tooling: `python -m pip install '.[dev,release]'`.
- Push access to both GitHub repos. PyPI publishing uses **Trusted Publishing**,
  so no PyPI token is needed anywhere.

---

## Release checklist

A full release usually means new data **and** a new `3dtk` version. For a
code-only release, skip steps 1–4.

### 1. Build and deposit the catalogue (in `database-build`)

The data lifecycle belongs to the producer. Follow `database-build`'s
`RELEASING.md`; it builds the catalogue, emits
`3domics-<data_version>.sqlite` plus a `.sha256` sidecar, and deposits a new
version under the catalogue concept DOI
[`10.5281/zenodo.22159111`](https://doi.org/10.5281/zenodo.22159111).

Never compute a release checksum from a local build: a local rebuild of
identical records has a different `source_snapshot` and therefore different
bytes.

### 2. Check the new release before adopting it

```bash
python scripts/sync_catalog.py --dry-run                       # what is latest?
python scripts/sync_catalog.py --dry-run --data-version <ver>  # resolve a pin
```

The script verifies the artefact against its `.sha256` sidecar and refuses a
catalogue whose `schema_version` this `3dtk` cannot read.

### 3. Adopt the new catalogue

```bash
python scripts/sync_catalog.py --data-version <data_version> --pin --download
```

`--pin` rewrites `PINNED_CATALOG` in `src/py3dtk/catalog.py`; `--download`
puts the verified artefact in the local cache so you can exercise it. Review the
diff: `data_version`, `schema_version`, `sha256`, `url`, `version_doi` and
`size_bytes` should all have moved together.

If `schema_version` changed, that is a **breaking data change**: update the
readers, add the new version to `SUPPORTED_SCHEMA_VERSIONS` in
`src/py3dtk/query.py`, and decide whether to keep reading the old one.

### 4. Verify against the real catalogue

```bash
3dtk database info                      # identity, size, SHA-256
3dtk                                    # per-level record counts
3dtk microsamples query --experiment-id G --sex female --columns context --limit 5
3dtk counts export --experiment-id G --level micro --csv | head -3
```

Confirm the record counts moved the way the data release notes say they did.

### 5. Write release notes

Add user-facing changes under `## [Unreleased]` in `CHANGELOG.md`.

### 6. Bump the version

Update the version in `pyproject.toml`, `CITATION.cff` and `codemeta.json`, and
cut the `[Unreleased]` changelog section into a dated release section.

### 7. Test, commit, tag, push

```bash
python -m pytest
python -m build && python -m twine check dist/*
git diff                                   # review every change
git commit -am "Release v<version>"
git tag v<version>
git push origin main && git push origin v<version>
```

### 8. PyPI publish and Zenodo archival (automatic)

Pushing the `v*` tag triggers `.github/workflows/release.yml`: it verifies the
pin, runs the tests, builds, validates, smoke-tests the wheel, publishes to PyPI
via Trusted Publishing, then creates a GitHub Release with the artefacts
attached.

The GitHub Release is what archives the **software** to Zenodo, via the
[Zenodo–GitHub integration](https://zenodo.org/account/settings/github/). That
is a *separate* concept from the **catalogue** concept DOI that
`database-build` deposits.

> **One-time setup**, before the first tag you want archived: enable
> `3d-omics/3dtk` at <https://zenodo.org/account/settings/github/>. Zenodo only
> archives Releases created *after* the webhook is enabled. Afterwards, add the
> software concept DOI to `CITATION.cff`, `codemeta.json` and the README.

---

## Outstanding tasks

- [x] **Data usage terms.** Since 0.1.1, `src/py3dtk/terms.py` states only what
      the catalogue records: the CC-BY-4.0 licence, the concept DOI to cite, and
      the issue tracker for questions. Extend `TERMS_MESSAGE` if the consortium
      agrees further terms.
- [ ] **`py3dtk` name reservation.** After the first release, publish a stub
      `py3dtk` distribution that simply depends on `3dtk`, so the import name
      cannot be squatted and `pip install py3dtk` works. Agreed as a post-v1
      step.
- [x] **Read the Docs.** Live at <https://3dtk.readthedocs.io/>, building from
      `.readthedocs.yaml` on every push to `main`.
- [ ] **Airtable link fields.** Specimen `treatment_group` contains raw Airtable
      record ids (`recMXDODTfnGcavHn`) rather than readable labels. `3dtk`
      displays `treatment` / `treatment_name` instead and keeps
      `treatment_group` filterable, but resolving the link is a
      `database-build` change.

## Rollback

- **Bad tag, not yet on PyPI:** delete the tag locally and remotely, fix, re-tag.
- **Already on PyPI:** versions cannot be re-uploaded. Yank the bad release and
  ship a patch. Never reuse a version number.
- **Bad catalogue pinned:** re-run `scripts/sync_catalog.py --data-version
  <previous> --pin` and ship a patch release. Because the pin is a version DOI,
  rolling back is exact.
- **Bad Zenodo deposit:** Zenodo versions are immutable once published. Publish a
  corrected new version under the same concept DOI rather than editing in place.
