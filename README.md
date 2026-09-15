# 3dtk — the 3D'omics ToolKit

[![CI](https://github.com/3d-omics/3dtk/actions/workflows/ci.yml/badge.svg)](https://github.com/3d-omics/3dtk/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/3dtk)](https://pypi.org/project/3dtk/)
[![Python versions](https://img.shields.io/pypi/pyversions/3dtk)](https://pypi.org/project/3dtk/)
[![Documentation](https://readthedocs.org/projects/3dtk/badge/?version=latest)](https://3dtk.readthedocs.io/)
[![Catalogue DOI](https://img.shields.io/badge/data%20DOI-10.5281%2Fzenodo.22159111-blue)](https://doi.org/10.5281/zenodo.22159111)
[![Licence](https://img.shields.io/badge/licence-GPLv3-blue)](LICENSE)

Find, summarise, export, and download records from the [3D'omics](https://3d-omics.eu)
data catalogue — from a command line and a Python API, with **no credentials and
no server**. `3dtk` reads a published, checksummed SQLite artefact deposited on
Zenodo under a citable DOI.

**Documentation:** <https://3dtk.readthedocs.io/>

```bash
pip install 3dtk
3dtk database sync          # fetch the catalogue once (59 MB, checksum-verified)
3dtk microsamples query --experiment-id G --sex female --columns context
```

## `pip install 3dtk` → `import py3dtk`

Python identifiers cannot begin with a digit, so `import 3dtk` is a
`SyntaxError`. The distribution and the console script are `3dtk`; the **import
package is `py3dtk`** — the same split as `scikit-learn` → `sklearn`.

| Surface | Name |
| --- | --- |
| PyPI distribution | `3dtk` |
| Console script | `3dtk` |
| Import package | `py3dtk` |

```python
import py3dtk

with py3dtk.Database() as db:
    genomes = db.genomes.query(quality="high", genus="Faeciplasma")
```

## The data

The catalogue is built from Airtable by
[`3d-omics/database-build`](https://github.com/3d-omics/database-build) and
published to Zenodo. `3dtk` is a **consumer**: it never talks to Airtable, never
rebuilds data, and holds no secrets.

| | |
| --- | --- |
| Cite this (always latest) | [`10.5281/zenodo.22159111`](https://doi.org/10.5281/zenodo.22159111) |
| Version this release pins | [`10.5281/zenodo.22159112`](https://doi.org/10.5281/zenodo.22159112) |
| `data_version` | `2026.08.29` |
| `schema_version` | `2` |
| Licence | CC-BY-4.0 |

A pinned build never silently follows "latest". The concept DOI is for
citation; the **version DOI is what the code pins**, together with the artefact's
SHA-256. A download that fails verification is discarded, never used.

### Where the catalogue comes from

`3dtk` resolves the catalogue in this order, and the first hit wins:

1. an explicit `--db` / `path=` argument,
2. the `PY3DTK_DB` environment variable,
3. the user cache (`3dtk database sync`, or a lazy first-use download),
4. a bundled package resource, if one was shipped.

The published wheel bundles **no** catalogue, so the first command that needs
data downloads it once into the cache. `3dtk database info` reports which source
was used; `3dtk database where` prints the path without downloading anything.

## The hierarchy

```
experiments → specimens → macrosamples → cryosections → microsamples
                                    ↘ genomes (per experiment)
                                    ↘ counts (genome × sample matrices)
```

Each level is a CLI group with the **same action grammar**, so learning one
teaches the rest:

| Action | What it does |
| --- | --- |
| `query` | list matching records |
| `values --field F` | count distinct values of `F` after filters |
| `stats` | summarise matches, with top-N breakdowns |
| `fields` | list the fields `values --field` accepts |
| `fetch` | download files (`macrosamples`, `microsamples`) |

`counts` adds `matrices` and `export`.

## What `3dtk` adds over the raw catalogue

**Denormalisation.** The catalogue stores each level separately. `3dtk` joins
them, so one query answers a cross-level question:

```bash
3dtk microsamples query --experiment-id G --sex female --columns context
```

returns each microsample with its host species, treatment, cryosection position
and spatial coordinates — a five-table join, expressed as one command.

**Dense count-matrix export.** The count tables are sparse: zeros are dropped,
about five-sixths of the microsample cells. `3dtk counts export` rebuilds the
dense matrix, restoring the zeros and following the original row and column
order recorded in `matrix_axes`:

```bash
3dtk counts export --cryosection-id G005bI205A --csv --output-file counts.csv \
                   --coordinates coords.csv
```

A genome whose row is entirely zero keeps its place — which is exactly why the
axes come from `matrix_axes` and not from `SELECT DISTINCT` over the sparse
rows. `--coordinates` writes a companion sample table aligned to the matrix
columns, so the pair drops straight into a spatial analysis.

Matrices within an experiment share a genome axis, so they merge:

```bash
3dtk counts export --experiment-id G --level micro --csv --output-file G.csv
```

**Spatial coordinates.** `x_coord`/`y_coord` (laser-microdissection stage) and
`pixel_x`/`pixel_y` (image) are carried through `query` output, filterable as a
bounding box, and available alongside abundances in an export:

```bash
3dtk microsamples query --x-min 13000 --x-max 14000 --y-min 18000 --y-max 19000 \
                        --columns spatial
```

## Downloading sequencing data

The catalogue stores ENA *browser links* and run accessions, not file URLs, so
`fetch` resolves them through the ENA Portal API — in batches, so a
500-microsample fetch issues a handful of requests rather than 500. ENA
publishes an MD5 per file, and every download is verified against it as well as
against a streaming gzip integrity check.

```bash
3dtk microsamples fetch --cryosection-id G005bI205A --output-dir data
3dtk microsamples fetch --experiment-id G --script download.sh   # batch instead
```

Every file is logged to an append-only JSONL manifest. Metabolomics macrosamples
point at MetaboLights rather than ENA; `3dtk` surfaces those accessions rather
than pretending it can download them.

## Python API

```python
import py3dtk

with py3dtk.Database() as db:
    db.specimens.count(sex="female")
    db.genomes.values("phylum", limit=5)
    db.microsamples.stats(experiment_id="G")

    matrix = db.counts.export(experiment_id="G", level="micro")
    coords = db.counts.coordinates(matrix)
```

Every collection supports `query`, `count`, `values` and `stats`;
`macrosamples` and `microsamples` add `fetch`; `counts` adds `matrices`,
`export` and `coordinates`.

## Documentation

Full documentation: <https://3dtk.readthedocs.io/>

## Development

```bash
git clone https://github.com/3d-omics/3dtk
cd 3dtk
python -m pip install -e ".[dev]"
python -m pytest
```

The test suite builds a miniature catalogue in a temp directory and makes no
network calls, so it runs offline and in seconds.

## Related repositories

| Repo | Role |
| --- | --- |
| [`3d-omics/3dtk`](https://github.com/3d-omics/3dtk) | this CLI and Python API |
| [`3d-omics/database-build`](https://github.com/3d-omics/database-build) | builds and publishes the catalogue |
| [`3d-omics/database`](https://github.com/3d-omics/database) | the public web portal |

`3dtk` follows the design of [`ehitk`](https://github.com/earthhologenome/ehitk),
the Earth Hologenome Initiative's toolkit.

## Licence

GPLv3 — see [LICENSE](LICENSE). The **data** is CC-BY-4.0; see the catalogue's
Zenodo record.
