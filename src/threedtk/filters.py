"""Declared CLI filter options, one list per target.

The same specifications drive every action of every target, so ``query``,
``values``, ``stats`` and ``fetch`` accept exactly the same filters -- a user who
learns ``microsamples query`` can drive ``microsamples stats`` without checking.
Filter names match the Python API's keyword arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FilterOption:
    """One CLI filter option and the query filter key it populates.

    Attributes:
        name: Filter key, matching the Python API keyword.
        type: Value type; ``bool`` becomes a ``--flag/--no-flag`` pair.
        help: Help text shown in ``--help``.
        decls: Extra CLI declarations, e.g. a short or aliased spelling.
    """

    name: str
    type: type
    help: str
    decls: tuple[str, ...] = field(default_factory=tuple)


def _identifier(name: str, label: str) -> FilterOption:
    return FilterOption(name, str, f"Exact {label}. Comma-separated values allowed.")


_EXPERIMENT_CONTEXT = [
    _identifier("experiment_id", "experiment ID"),
]

_SPECIMEN_CONTEXT = [
    _identifier("specimen_id", "specimen ID"),
    *_EXPERIMENT_CONTEXT,
    FilterOption("species", str, "Host species, scientific or common name."),
    _identifier("taxid", "host NCBI taxon ID"),
    _identifier("sex", "host sex"),
    _identifier("treatment", "treatment code, e.g. TC1"),
    _identifier("treatment_group", "treatment group (an Airtable record id)"),
    _identifier("lifestage", "host life stage"),
]

FILTERS: dict[str, list[FilterOption]] = {
    "experiments": [
        *_EXPERIMENT_CONTEXT,
        _identifier("experiment_type", "experiment type"),
        FilterOption(
            "has_genome_catalogue",
            bool,
            "Only experiments that do (or do not) have a genome catalogue.",
            ("--has-genome-catalogue/--no-genome-catalogue",),
        ),
    ],
    "specimens": [
        *_SPECIMEN_CONTEXT,
        _identifier("pen", "pen"),
        FilterOption("weight_min", float, "Minimum specimen weight."),
        FilterOption("weight_max", float, "Maximum specimen weight."),
        FilterOption("dpi_min", int, "Minimum days post infection."),
        FilterOption("dpi_max", int, "Maximum days post infection."),
    ],
    "macrosamples": [
        _identifier("macrosample_id", "macrosample ID"),
        *_SPECIMEN_CONTEXT,
        _identifier("data_type", "data type, e.g. Metagenomics or Metabolomics"),
        _identifier("sample_type", "sample type, e.g. Caecum"),
        _identifier("preservative", "preservative"),
        _identifier("container", "container"),
        _identifier("code", "macrosample code"),
        _identifier("library_id", "sequencing library ID"),
        _identifier("ena_accession", "ENA accession"),
        _identifier("metabolights_accession", "MetaboLights accession"),
        FilterOption(
            "has_ena",
            bool,
            "Only macrosamples that do (or do not) carry an ENA accession.",
            ("--has-ena/--no-ena",),
        ),
        FilterOption(
            "has_metabolights",
            bool,
            "Only macrosamples that do (or do not) carry a MetaboLights accession.",
            ("--has-metabolights/--no-metabolights",),
        ),
    ],
    "cryosections": [
        _identifier("cryosection_id", "cryosection ID"),
        _identifier("macrosample_id", "macrosample ID"),
        *_SPECIMEN_CONTEXT,
        _identifier("position", "cryosection position"),
        _identifier("slide", "slide"),
        _identifier("sample_type", "sample type"),
        FilterOption(
            "has_image",
            bool,
            "Only cryosections that do (or do not) have an image.",
            ("--has-image/--no-image",),
        ),
    ],
    "microsamples": [
        _identifier("microsample_id", "microsample ID, e.g. G121eI102A003"),
        _identifier("library_id", "sequencing library ID, e.g. M300653"),
        _identifier("cryosection_id", "cryosection ID"),
        _identifier("macrosample_id", "macrosample ID"),
        *_SPECIMEN_CONTEXT,
        _identifier("sample_type", "microsample type, e.g. Positive"),
        _identifier("collection_method", "collection method"),
        _identifier("lm_batch", "laser microdissection batch"),
        _identifier("shape", "capture shape"),
        _identifier("ena_accession", "ENA accession"),
        FilterOption("size_min", float, "Minimum microsample size."),
        FilterOption("size_max", float, "Maximum microsample size."),
        FilterOption("x_min", float, "Bounding box: minimum x_coord."),
        FilterOption("x_max", float, "Bounding box: maximum x_coord."),
        FilterOption("y_min", float, "Bounding box: minimum y_coord."),
        FilterOption("y_max", float, "Bounding box: maximum y_coord."),
        FilterOption("pixel_x_min", int, "Bounding box: minimum pixel_x."),
        FilterOption("pixel_x_max", int, "Bounding box: maximum pixel_x."),
        FilterOption("pixel_y_min", int, "Bounding box: minimum pixel_y."),
        FilterOption("pixel_y_max", int, "Bounding box: maximum pixel_y."),
        FilterOption(
            "has_sequencing",
            bool,
            "Only microsamples that do (or do not) have a sequencing run.",
            ("--has-sequencing/--no-sequencing",),
        ),
    ],
    "genomes": [
        _identifier("genome", "genome ID, e.g. D300418:bin_000001"),
        *_EXPERIMENT_CONTEXT,
        FilterOption(
            "quality", str, "Derived quality tier: high, medium, or low."
        ),
        _identifier("domain", "GTDB domain, with or without the d__ prefix"),
        _identifier("phylum", "GTDB phylum, with or without the p__ prefix"),
        FilterOption(
            "class_",
            str,
            "Exact GTDB class, with or without the c__ prefix.",
            ("--class",),
        ),
        _identifier("order", "GTDB order, with or without the o__ prefix"),
        _identifier("family", "GTDB family, with or without the f__ prefix"),
        _identifier("genus", "GTDB genus, with or without the g__ prefix"),
        _identifier("species", "GTDB species, with or without the s__ prefix"),
        FilterOption("completeness_min", float, "Minimum completeness."),
        FilterOption("completeness_max", float, "Maximum completeness."),
        FilterOption("contamination_min", float, "Minimum contamination."),
        FilterOption("contamination_max", float, "Maximum contamination."),
        FilterOption("length_min", int, "Minimum genome length."),
        FilterOption("length_max", int, "Maximum genome length."),
    ],
    "counts": [
        FilterOption("level", str, "Count level: macro or micro."),
        *_EXPERIMENT_CONTEXT,
        _identifier("cryosection_id", "cryosection ID"),
        _identifier("genome", "genome ID"),
        _identifier("sample", "sample column: a library ID"),
        _identifier("specimen_id", "specimen ID"),
        _identifier("macrosample_id", "macrosample ID"),
        _identifier("sample_type", "sample type"),
        _identifier("domain", "GTDB domain"),
        _identifier("phylum", "GTDB phylum"),
        FilterOption("class_", str, "Exact GTDB class.", ("--class",)),
        _identifier("order", "GTDB order"),
        _identifier("family", "GTDB family"),
        _identifier("genus", "GTDB genus"),
        _identifier("species", "GTDB species"),
        FilterOption("count_min", float, "Minimum count value."),
        FilterOption("count_max", float, "Maximum count value."),
        FilterOption("x_min", float, "Bounding box: minimum x_coord."),
        FilterOption("x_max", float, "Bounding box: maximum x_coord."),
        FilterOption("y_min", float, "Bounding box: minimum y_coord."),
        FilterOption("y_max", float, "Bounding box: maximum y_coord."),
    ],
}

#: Filter keys whose CLI name differs from the query filter key.
FILTER_KEY_OVERRIDES = {"class_": "class"}


def filter_key(name: str) -> str:
    """Map a CLI parameter name to its query filter key."""
    return FILTER_KEY_OVERRIDES.get(name, name)
