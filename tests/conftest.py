"""A miniature catalogue fixture, built in a temp dir so tests need no network.

The fixture mirrors the real schema rather than simplifying it, because the
behaviours worth testing are the awkward ones:

* ``microsamples`` and ``microsample_sequencing`` use different
  ``microsample_id`` namespaces and are joined on the ENA accession;
* the count tables are sparse, so a genome with an all-zero row exists only in
  ``matrix_axes``;
* ``source_files.row_count`` records the non-zero cell count, which is the
  round-trip invariant;
* a cryosection referenced by a microsample can be missing from
  ``cryosections`` (the real catalogue has 185 such references).
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

SCHEMA = """
CREATE TABLE "experiments" ("airtable_record_id" TEXT, "airtable_created_time" TEXT,
  "experiment_id" TEXT, "name" TEXT, "type" TEXT, "start_date" TEXT, "end_date" TEXT,
  "description" TEXT, "bioproject_accession" TEXT, "bioproject_link" TEXT,
  "mag_description" TEXT, "mag_completeness_avg" REAL, "mag_contamination_avg" REAL,
  "mag_new_species_pct" REAL, "mag_count" INTEGER, "doi" TEXT, "link" TEXT,
  "has_genome_catalogue" INTEGER NOT NULL DEFAULT 0);
CREATE TABLE "specimens" ("airtable_record_id" TEXT, "airtable_created_time" TEXT,
  "specimen_id" TEXT, "biosample_accession" TEXT, "biosample_link" TEXT,
  "experiment_id" TEXT, "experiment_record_id" TEXT, "pen" TEXT,
  "slaughtering_date" TEXT, "slaughtering_day_count" INTEGER, "treatment_name" TEXT,
  "treatment" TEXT, "weight" REAL, "dpi" INTEGER, "treatment_group" TEXT, "sex" TEXT,
  "species_scientific" TEXT, "species_common" TEXT, "taxid" TEXT, "lifestage" TEXT);
CREATE TABLE "macrosamples" ("airtable_record_id" TEXT, "airtable_created_time" TEXT,
  "macrosample_id" TEXT, "code" TEXT, "container" TEXT, "data_type" TEXT,
  "description" TEXT, "ena_accession" TEXT, "ena_link" TEXT, "specimen_id" TEXT,
  "preservative" TEXT, "sample_type" TEXT, "metabolights_accession" TEXT,
  "metabolights_link" TEXT);
CREATE TABLE "cryosections" ("airtable_record_id" TEXT, "airtable_created_time" TEXT,
  "cryosection_id" TEXT, "macrosample_id" TEXT, "microsample_count" INTEGER,
  "position" TEXT, "slide_date" TEXT, "slide" TEXT,
  "has_image" INTEGER NOT NULL DEFAULT 0);
CREATE TABLE "microsamples" ("airtable_record_id" TEXT, "airtable_created_time" TEXT,
  "microsample_id" TEXT, "collection_method" TEXT, "cryosection_id" TEXT, "date" TEXT,
  "ena_accession" TEXT, "ena_link" TEXT, "lm_batch" TEXT, "size" REAL,
  "x_coord" REAL, "y_coord" REAL, "sample_type" TEXT);
CREATE TABLE "microsample_sequencing" ("airtable_record_id" TEXT,
  "airtable_created_time" TEXT, "microsample_id" TEXT, "cryosection_id" TEXT,
  "shape" TEXT, "size" REAL, "pixel_x" INTEGER, "pixel_y" INTEGER, "ena_link" TEXT,
  "run_accession" TEXT);
CREATE TABLE "macrosample_sequencing" ("airtable_record_id" TEXT,
  "airtable_created_time" TEXT, "library_id" TEXT, "ena_link" TEXT,
  "run_accession" TEXT, "experimental_unit" TEXT);
CREATE TABLE "source_files" (source_id TEXT PRIMARY KEY, table_name TEXT NOT NULL,
  attachment_key TEXT NOT NULL, target_table TEXT, owner_column TEXT NOT NULL,
  owner_value TEXT, filename TEXT NOT NULL, sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL, row_count INTEGER, kind TEXT NOT NULL,
  airtable_record_id TEXT NOT NULL);
CREATE TABLE "matrix_axes" (source_id TEXT NOT NULL, axis TEXT NOT NULL,
  position INTEGER NOT NULL, key TEXT NOT NULL, PRIMARY KEY (source_id, axis, position));
CREATE TABLE "genome_metadata" ("experiment_id" TEXT, "source_id" TEXT, "genome" TEXT,
  "domain" TEXT, "phylum" TEXT, "class" TEXT, "order" TEXT, "family" TEXT,
  "genus" TEXT, "species" TEXT, "completeness" REAL, "contamination" REAL,
  "length" INTEGER);
CREATE TABLE "macro_genome_counts" ("experiment_id" TEXT, "source_id" TEXT,
  "genome" TEXT, "macrosample" TEXT, "count" REAL);
CREATE TABLE "microsample_counts" ("cryosection_id" TEXT, "source_id" TEXT,
  "genome" TEXT, "microsample" TEXT, "count" REAL);
CREATE TABLE "catalog_meta" (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIEW "experiments_with_genomes" AS
  SELECT * FROM "experiments" WHERE "has_genome_catalogue" = 1;
CREATE VIEW "cryosections_with_image" AS
  SELECT * FROM "cryosections" WHERE "has_image" = 1;
"""

#: Non-zero cells of the micro matrix. Genome ``X:bin_2`` is deliberately absent
#: from every cell, so it exists only on the ``matrix_axes`` row axis.
MICRO_CELLS = [
    ("X:bin_1", "M001", 10.5),
    ("X:bin_1", "M003", 3.25),
    ("X:bin_3", "M002", 7.0),
]
MICRO_GENOMES = ["X:bin_1", "X:bin_2", "X:bin_3"]
MICRO_SAMPLES = ["M001", "M002", "M003"]
MICRO_SOURCE = "recX/cryo1.csv"

MACRO_CELLS = [("X:bin_1", "LIB1", 42.0)]
MACRO_GENOMES = ["X:bin_1", "X:bin_2", "X:bin_3"]
MACRO_SAMPLES = ["LIB1", "LIB2"]
MACRO_SOURCE = "recX/experiment_X_counts.csv"


def build_catalog(path: Path, *, schema_version: str | None = "2") -> Path:
    """Write a miniature catalogue to ``path`` and return it."""
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)

        connection.execute(
            'INSERT INTO experiments ("experiment_id", "name", "type", "start_date", '
            '"mag_count", "mag_completeness_avg", "mag_contamination_avg", '
            '"has_genome_catalogue") VALUES (?,?,?,?,?,?,?,?)',
            ("X", "Experiment X", "trial", "2026-01-01", 3, 88.0, 2.0, 1),
        )
        connection.execute(
            'INSERT INTO experiments ("experiment_id", "name", "type", '
            '"has_genome_catalogue") VALUES (?,?,?,?)',
            ("Y", "Experiment Y", "pilot", 0),
        )

        connection.executemany(
            'INSERT INTO specimens ("specimen_id", "experiment_id", "sex", '
            '"species_scientific", "species_common", "taxid", "weight", "dpi", "pen", '
            '"treatment", "treatment_name", "treatment_group", "biosample_accession", '
            '"lifestage") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            [
                ("X01", "X", "female", "Gallus gallus", "chicken", "9031", 1.5, 7,
                 "P1", "TX1", "ControlDiet", "recAAAAAAAAAAAAAA", "SAMEA1", "adult"),
                ("X02", "X", "male", "Gallus gallus", "chicken", "9031", 2.5, 14,
                 "P2", "TX2", "TreatedDiet", "recBBBBBBBBBBBBBB", "SAMEA2", "adult"),
            ],
        )

        connection.executemany(
            'INSERT INTO macrosamples ("macrosample_id", "specimen_id", "data_type", '
            '"sample_type", "ena_accession", "ena_link", "metabolights_accession", '
            '"preservative", "container", "code") VALUES (?,?,?,?,?,?,?,?,?,?)',
            [
                ("X01aF", "X01", "Metagenomics", "Caecum", "ERRM1",
                 "https://www.ebi.ac.uk/ena/browser/view/ERRM1", "", "None", "2 mL tube", "F"),
                ("X01aI", "X01", "Metabolomics", "Caecum", "", "", "MTBLS1",
                 "None", "5 mL tube", "I"),
            ],
        )
        connection.executemany(
            'INSERT INTO macrosample_sequencing ("library_id", "run_accession", '
            '"experimental_unit") VALUES (?,?,?)',
            [("LIB1", "ERRM1", "X01"), ("LIB2", "", "X02")],
        )

        connection.execute(
            'INSERT INTO cryosections ("cryosection_id", "macrosample_id", '
            '"microsample_count", "position", "slide", "has_image") VALUES (?,?,?,?,?,?)',
            ("CRYO1", "X01aF", 3, "A", "S1", 1),
        )

        # ORPHAN references a cryosection that does not exist, as the real
        # catalogue does for 185 microsamples.
        connection.executemany(
            'INSERT INTO microsamples ("microsample_id", "cryosection_id", '
            '"ena_accession", "ena_link", "sample_type", "size", "x_coord", "y_coord", '
            '"collection_method", "lm_batch") VALUES (?,?,?,?,?,?,?,?,?,?)',
            [
                ("CRYO1-001", "CRYO1", "ERR1", "https://www.ebi.ac.uk/ena/browser/view/ERR1",
                 "Positive", 100.0, 10.0, 20.0, "LMD", "B1"),
                ("CRYO1-002", "CRYO1", "ERR2", "https://www.ebi.ac.uk/ena/browser/view/ERR2",
                 "Positive", 110.0, 30.0, 40.0, "LMD", "B1"),
                ("CRYO1-003", "CRYO1", "ERR3", "https://www.ebi.ac.uk/ena/browser/view/ERR3",
                 "NegativeMembrane", 90.0, 50.0, 60.0, "LMD", "B1"),
                ("ORPHAN-001", "MISSING", "", "", "Positive", 80.0, None, None, "LMD", "B2"),
            ],
        )
        connection.executemany(
            'INSERT INTO microsample_sequencing ("microsample_id", "cryosection_id", '
            '"shape", "pixel_x", "pixel_y", "run_accession") VALUES (?,?,?,?,?,?)',
            [
                ("M001", "CRYO1", "Elipse", 1, 2, "ERR1"),
                ("M002", "CRYO1", "Elipse", 3, 4, "ERR2"),
                ("M003", "CRYO1", "Elipse", 5, 6, "ERR3"),
            ],
        )

        connection.executemany(
            'INSERT INTO genome_metadata ("experiment_id", "source_id", "genome", '
            '"domain", "phylum", "class", "order", "family", "genus", "species", '
            '"completeness", "contamination", "length") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            [
                ("X", "recX/meta.csv", "X:bin_1", "d__Bacteria", "p__Bacillota_A",
                 "c__Clostridia", "o__Oscillospirales", "f__Acutalibacteraceae",
                 "g__Faeciplasma", "s__Faeciplasma gallinarum", 99.5, 0.2, 2_000_000),
                ("X", "recX/meta.csv", "X:bin_2", "d__Bacteria", "p__Bacteroidota",
                 "c__Bacteroidia", "o__Bacteroidales", "f__Bacteroidaceae",
                 "g__Bacteroides", "s__Bacteroides fragilis", 75.0, 6.0, 3_000_000),
                ("X", "recX/meta.csv", "X:bin_3", "d__Bacteria", "p__Bacillota",
                 "c__Bacilli", "o__Lactobacillales", "f__Lactobacillaceae",
                 "g__Limosilactobacillus", "s__Limosilactobacillus reuteri",
                 40.0, 12.0, 1_500_000),
            ],
        )

        connection.executemany(
            "INSERT INTO microsample_counts VALUES (?,?,?,?,?)",
            [("CRYO1", MICRO_SOURCE, genome, sample, value)
             for genome, sample, value in MICRO_CELLS],
        )
        connection.executemany(
            "INSERT INTO macro_genome_counts VALUES (?,?,?,?,?)",
            [("X", MACRO_SOURCE, genome, sample, value)
             for genome, sample, value in MACRO_CELLS],
        )

        for source, target, owner_column, owner, filename, genomes, samples, cells in (
            (MICRO_SOURCE, "microsample_counts", "cryosection_id", "CRYO1",
             "cryo1.csv", MICRO_GENOMES, MICRO_SAMPLES, MICRO_CELLS),
            (MACRO_SOURCE, "macro_genome_counts", "experiment_id", "X",
             "experiment_X_counts.csv", MACRO_GENOMES, MACRO_SAMPLES, MACRO_CELLS),
        ):
            connection.execute(
                "INSERT INTO source_files VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (source, owner_column.split("_")[0] + "s", "counts", target,
                 owner_column, owner, filename, "0" * 64, 1024, len(cells),
                 "csv_matrix", "recX"),
            )
            connection.execute(
                "INSERT INTO matrix_axes VALUES (?,?,?,?)", (source, "key", 0, "genome")
            )
            connection.executemany(
                "INSERT INTO matrix_axes VALUES (?,?,?,?)",
                [(source, "row", position, key) for position, key in enumerate(genomes)],
            )
            connection.executemany(
                "INSERT INTO matrix_axes VALUES (?,?,?,?)",
                [(source, "column", position, key) for position, key in enumerate(samples)],
            )

        meta = [
            ("data_version", "2026.01.01"),
            ("built_with_3domics_db_build", "0.1.0"),
            ("source_snapshot", "2026-01-01T00:00:00Z"),
        ]
        if schema_version is not None:
            meta.append(("schema_version", schema_version))
        connection.executemany("INSERT INTO catalog_meta VALUES (?,?)", meta)
        connection.commit()
    finally:
        connection.close()
    return path


@pytest.fixture(scope="session")
def catalog(tmp_path_factory) -> Path:
    """A miniature catalogue shared across the test session."""
    return build_catalog(tmp_path_factory.mktemp("catalog") / "3domics-test.sqlite")


@pytest.fixture(autouse=True)
def isolate_catalog_resolution(monkeypatch, tmp_path):
    """Keep tests off the network and out of the user's real cache."""
    monkeypatch.delenv("PY3DTK_DB", raising=False)
    monkeypatch.setattr("py3dtk.catalog.cache_dir", lambda: tmp_path / "cache")

    def _no_network(*args, **kwargs):
        raise AssertionError("tests must not download the catalogue")

    monkeypatch.setattr("py3dtk.catalog.download_catalog", _no_network)
