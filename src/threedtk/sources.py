"""Denormalised SQL sources for each query target.

The catalogue stores every level of the 3D'omics hierarchy in its own table::

    experiments -> specimens -> macrosamples -> cryosections -> microsamples
                                          \\-> genomes (per experiment)
                                          \\-> counts (genome x sample matrices)

Researchers ask questions that cross those levels ("every microsample from
female specimens in experiment G, with host species, treatment group,
cryosection position and spatial coordinates"), so each target below is an
inline join that carries parent metadata down to the child row. These joins
live in the consumer on purpose -- adding views to ``database-build`` would
couple the data artefact to one client's query shape.

Two things about the catalogue drive the design:

**The ENA run accession is the bridge between identifier namespaces.**
``microsamples.microsample_id`` (e.g. ``G121eI102A003``) and
``microsample_sequencing.microsample_id`` (e.g. ``M300653``) are *different*
namespaces and share no values. The tables join on
``microsamples.ena_accession = microsample_sequencing.run_accession`` instead,
which matches all 4,463 sequencing rows one-to-one. The same holds for
``macrosamples.ena_accession = macrosample_sequencing.run_accession`` (652
rows). Without this bridge the laser-capture coordinates and the sequencing
libraries could not appear on the same row.

**Counts are keyed by library, not by sample.** ``macro_genome_counts.macrosample``
holds ``macrosample_sequencing.library_id`` values and
``microsample_counts.microsample`` holds ``microsample_sequencing.microsample_id``
values, so both count tables reach their sample metadata through the sequencing
table and then across the accession bridge.

Every join is a ``LEFT JOIN``: the catalogue has real referential gaps (185
``cryosection_id`` values referenced by ``microsamples`` are absent from
``cryosections``; 289 of the libraries named in ``microsample_counts`` have no
``microsample_sequencing`` row), and dropping those rows would silently
under-report.
"""

from __future__ import annotations

EXPERIMENTS_SOURCE = """
(
    SELECT
        e."experiment_id",
        e."name" AS "experiment_name",
        e."type" AS "experiment_type",
        e."start_date",
        e."end_date",
        e."description",
        e."bioproject_accession",
        e."bioproject_link",
        e."mag_description",
        e."mag_completeness_avg",
        e."mag_contamination_avg",
        e."mag_new_species_pct",
        e."mag_count",
        e."doi",
        e."link",
        e."has_genome_catalogue"
    FROM "experiments" AS e
)
"""

SPECIMENS_SOURCE = """
(
    SELECT
        s."specimen_id",
        s."experiment_id",
        e."name" AS "experiment_name",
        e."type" AS "experiment_type",
        s."biosample_accession",
        s."biosample_link",
        s."pen",
        s."slaughtering_date",
        s."slaughtering_day_count",
        s."treatment",
        s."treatment_name",
        s."treatment_group",
        s."weight",
        s."dpi",
        s."sex",
        s."species_scientific",
        s."species_common",
        s."taxid",
        s."lifestage"
    FROM "specimens" AS s
    LEFT JOIN "experiments" AS e ON s."experiment_id" = e."experiment_id"
)
"""

MACROSAMPLES_SOURCE = """
(
    SELECT
        ma."macrosample_id",
        ma."code",
        ma."container",
        ma."data_type",
        ma."description",
        ma."preservative",
        ma."sample_type",
        ma."ena_accession",
        ma."ena_link",
        ma."metabolights_accession",
        ma."metabolights_link",
        q."library_id",
        q."run_accession",
        q."experimental_unit",
        ma."specimen_id",
        s."experiment_id",
        e."name" AS "experiment_name",
        s."pen",
        s."dpi",
        s."treatment",
        s."treatment_group",
        s."weight" AS "specimen_weight",
        s."sex",
        s."species_scientific",
        s."species_common",
        s."taxid",
        s."lifestage"
    FROM "macrosamples" AS ma
    LEFT JOIN "specimens" AS s ON ma."specimen_id" = s."specimen_id"
    LEFT JOIN "experiments" AS e ON s."experiment_id" = e."experiment_id"
    LEFT JOIN "macrosample_sequencing" AS q
        ON ma."ena_accession" IS NOT NULL
        AND ma."ena_accession" <> ''
        AND ma."ena_accession" = q."run_accession"
)
"""

CRYOSECTIONS_SOURCE = """
(
    SELECT
        c."cryosection_id",
        c."macrosample_id",
        c."microsample_count",
        c."position",
        c."slide",
        c."slide_date",
        c."has_image",
        ma."sample_type",
        ma."data_type",
        ma."specimen_id",
        s."experiment_id",
        e."name" AS "experiment_name",
        s."treatment",
        s."treatment_group",
        s."sex",
        s."species_scientific",
        s."species_common",
        s."taxid",
        s."lifestage"
    FROM "cryosections" AS c
    LEFT JOIN "macrosamples" AS ma ON c."macrosample_id" = ma."macrosample_id"
    LEFT JOIN "specimens" AS s ON ma."specimen_id" = s."specimen_id"
    LEFT JOIN "experiments" AS e ON s."experiment_id" = e."experiment_id"
)
"""

MICROSAMPLES_SOURCE = """
(
    SELECT
        mi."microsample_id",
        mi."cryosection_id",
        mi."collection_method",
        mi."date",
        mi."lm_batch",
        mi."sample_type",
        mi."size",
        mi."x_coord",
        mi."y_coord",
        mi."ena_accession",
        mi."ena_link",
        q."microsample_id" AS "library_id",
        q."run_accession",
        q."shape",
        q."pixel_x",
        q."pixel_y",
        c."macrosample_id",
        c."position" AS "cryosection_position",
        c."slide",
        c."slide_date",
        ma."specimen_id",
        ma."sample_type" AS "macrosample_type",
        ma."data_type",
        s."experiment_id",
        e."name" AS "experiment_name",
        s."pen",
        s."dpi",
        s."treatment",
        s."treatment_group",
        s."sex",
        s."species_scientific",
        s."species_common",
        s."taxid",
        s."lifestage"
    FROM "microsamples" AS mi
    LEFT JOIN "microsample_sequencing" AS q
        ON mi."ena_accession" IS NOT NULL
        AND mi."ena_accession" <> ''
        AND mi."ena_accession" = q."run_accession"
    LEFT JOIN "cryosections" AS c ON mi."cryosection_id" = c."cryosection_id"
    LEFT JOIN "macrosamples" AS ma ON c."macrosample_id" = ma."macrosample_id"
    LEFT JOIN "specimens" AS s ON ma."specimen_id" = s."specimen_id"
    LEFT JOIN "experiments" AS e ON s."experiment_id" = e."experiment_id"
)
"""

GENOMES_SOURCE = """
(
    SELECT
        g."genome",
        g."experiment_id",
        e."name" AS "experiment_name",
        g."source_id",
        g."domain",
        g."phylum",
        g."class",
        g."order",
        g."family",
        g."genus",
        g."species",
        g."completeness",
        g."contamination",
        g."length"
    FROM "genome_metadata" AS g
    LEFT JOIN "experiments" AS e ON g."experiment_id" = e."experiment_id"
)
"""

#: One row per non-zero count cell, at either level, with genome taxonomy and
#: sample coordinates attached. ``level`` discriminates the two count tables.
COUNTS_SOURCE = """
(
    SELECT
        'macro' AS "level",
        mc."experiment_id",
        NULL AS "cryosection_id",
        mc."source_id",
        mc."genome",
        mc."macrosample" AS "sample",
        mc."count",
        ms."experimental_unit" AS "specimen_id",
        ma."macrosample_id",
        ma."sample_type",
        NULL AS "x_coord",
        NULL AS "y_coord",
        NULL AS "pixel_x",
        NULL AS "pixel_y",
        gm."domain",
        gm."phylum",
        gm."class",
        gm."order",
        gm."family",
        gm."genus",
        gm."species",
        gm."completeness",
        gm."contamination"
    FROM "macro_genome_counts" AS mc
    LEFT JOIN "macrosample_sequencing" AS ms ON mc."macrosample" = ms."library_id"
    LEFT JOIN "macrosamples" AS ma
        ON ma."ena_accession" IS NOT NULL
        AND ma."ena_accession" <> ''
        AND ma."ena_accession" = ms."run_accession"
    LEFT JOIN "genome_metadata" AS gm
        ON gm."genome" = mc."genome" AND gm."experiment_id" = mc."experiment_id"

    UNION ALL

    SELECT
        'micro' AS "level",
        s."experiment_id",
        uc."cryosection_id",
        uc."source_id",
        uc."genome",
        uc."microsample" AS "sample",
        uc."count",
        ma."specimen_id",
        c."macrosample_id",
        mi."sample_type",
        mi."x_coord",
        mi."y_coord",
        q."pixel_x",
        q."pixel_y",
        gm."domain",
        gm."phylum",
        gm."class",
        gm."order",
        gm."family",
        gm."genus",
        gm."species",
        gm."completeness",
        gm."contamination"
    FROM "microsample_counts" AS uc
    LEFT JOIN "microsample_sequencing" AS q ON uc."microsample" = q."microsample_id"
    LEFT JOIN "microsamples" AS mi
        ON mi."ena_accession" IS NOT NULL
        AND mi."ena_accession" <> ''
        AND mi."ena_accession" = q."run_accession"
    LEFT JOIN "cryosections" AS c ON uc."cryosection_id" = c."cryosection_id"
    LEFT JOIN "macrosamples" AS ma ON c."macrosample_id" = ma."macrosample_id"
    LEFT JOIN "specimens" AS s ON ma."specimen_id" = s."specimen_id"
    LEFT JOIN "genome_metadata" AS gm
        ON gm."genome" = uc."genome" AND gm."experiment_id" = s."experiment_id"
)
"""
