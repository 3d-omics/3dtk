"""Per-target statistics."""

from __future__ import annotations

import pytest
from rich.console import Console

from py3dtk.stats import STATS, render_target_stats, target_stats


@pytest.mark.parametrize("target", sorted(STATS))
def test_every_target_produces_stats(catalog, target) -> None:
    stats = target_stats(catalog_path=str(catalog), target=target)
    assert stats.empty_message is None, f"{target} matched nothing"
    assert stats.summary_labels
    assert stats.summary[STATS[target].matched_key] > 0


@pytest.mark.parametrize("target", sorted(STATS))
def test_every_target_renders_without_error(catalog, target) -> None:
    render_target_stats(
        Console(quiet=True), catalog_path=str(catalog), target=target
    )


def test_ranges_are_formatted_from_avg_min_max(catalog) -> None:
    stats = target_stats(catalog_path=str(catalog), target="genomes")
    labels = dict((key, label) for label, key in stats.summary_labels)
    assert "completeness_range" in labels
    assert stats.summary["min_completeness"] == 40.0
    assert stats.summary["max_completeness"] == 99.5


def test_specimen_stats_group_by_readable_treatment_names(catalog) -> None:
    """treatment_group holds Airtable record ids, so displays use treatment_name."""
    stats = target_stats(catalog_path=str(catalog), target="specimens")
    treatments = next(b for b in stats.breakdowns if b.title == "Treatments")
    assert {row["value"] for row in treatments.rows} == {"ControlDiet", "TreatedDiet"}


def test_filters_narrow_the_summary(catalog) -> None:
    stats = target_stats(
        catalog_path=str(catalog), target="genomes", filters={"quality": "high"}
    )
    assert stats.summary["matched_genomes"] == 1


def test_no_matches_yields_an_empty_message(catalog) -> None:
    stats = target_stats(
        catalog_path=str(catalog), target="genomes", filters={"genus": "Nope"}
    )
    assert stats.empty_message
    assert stats.breakdowns == ()


def test_unknown_target_is_rejected(catalog) -> None:
    with pytest.raises(ValueError):
        target_stats(catalog_path=str(catalog), target="hologenomes")
