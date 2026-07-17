from __future__ import annotations

import pytest

from services.simulation.engine import run_matchup_simulation
from services.trades.evaluator import (
    aggregate_window_deltas,
    build_variant_lineup,
    paired_delta_samples,
    summarize_delta,
)


def sample_lineup() -> list[dict[str, object]]:
    return [
        {"hitter_id": "hitter_1", "hitter_name": "Leadoff, Larry", "batting_side": "L", "lineup_spot": 1},
        {"hitter_id": "hitter_2", "hitter_name": "Contact, Carl", "batting_side": "R", "lineup_spot": 2},
        {"hitter_id": "hitter_3", "hitter_name": "Slugger, Sam", "batting_side": "R", "lineup_spot": 3},
    ]


def projection(home_run_rate: float) -> dict[str, float]:
    return {
        "estimated_bb_rate": 0.08,
        "estimated_k_rate": 0.22,
        "single_rate": 0.15,
        "double_rate": 0.05,
        "triple_rate": 0.005,
        "home_run_rate": home_run_rate,
        "out_in_play_rate": 0.45,
        "hard_hit_rate_on_contact": 0.35,
    }


def test_build_variant_lineup_swaps_at_same_spot() -> None:
    incoming = {"hitter_id": "hitter_9", "hitter_name": "Acquired, Andy", "batting_side": "S"}
    variant = build_variant_lineup(sample_lineup(), "hitter_2", incoming)

    assert [hitter["hitter_id"] for hitter in variant] == ["hitter_1", "hitter_9", "hitter_3"]
    assert variant[1]["lineup_spot"] == 2
    assert variant[1]["hitter_name"] == "Acquired, Andy"
    assert variant[1]["batting_side"] == "S"
    assert variant[0] == sample_lineup()[0]
    assert variant[2] == sample_lineup()[2]


def test_build_variant_lineup_defaults_missing_batting_side_to_right() -> None:
    incoming = {"hitter_id": "hitter_9", "hitter_name": "Acquired, Andy", "batting_side": None}
    variant = build_variant_lineup(sample_lineup(), "hitter_2", incoming)
    assert variant[1]["batting_side"] == "R"


def test_build_variant_lineup_rejects_missing_displaced_hitter() -> None:
    incoming = {"hitter_id": "hitter_9", "hitter_name": "Acquired, Andy", "batting_side": "R"}
    with pytest.raises(ValueError, match="hitter_404 is not in the projected lineup"):
        build_variant_lineup(sample_lineup(), "hitter_404", incoming)


def test_build_variant_lineup_rejects_incoming_hitter_already_in_lineup() -> None:
    incoming = {"hitter_id": "hitter_3", "hitter_name": "Slugger, Sam", "batting_side": "R"}
    with pytest.raises(ValueError, match="hitter_3 is already in the projected lineup"):
        build_variant_lineup(sample_lineup(), "hitter_2", incoming)


def test_paired_delta_samples_subtracts_per_iteration() -> None:
    deltas = paired_delta_samples([3.0, 5.0, 2.0], [4.0, 4.0, 6.0])
    assert deltas == [1.0, -1.0, 4.0]


def test_paired_delta_samples_rejects_mismatched_iteration_counts() -> None:
    with pytest.raises(ValueError, match="same iteration count"):
        paired_delta_samples([1.0, 2.0], [1.0])


def test_paired_delta_samples_rejects_empty_samples() -> None:
    with pytest.raises(ValueError, match="empty simulation samples"):
        paired_delta_samples([], [])


def test_summarize_delta_reports_mean_percentiles_and_mean_ci() -> None:
    summary = summarize_delta([1.0, -1.0, 4.0, 0.0])
    assert summary["mean"] == 1.0
    assert summary["p10"] <= summary["p50"] <= summary["p90"]
    assert summary["mean_ci_low"] < summary["mean"] < summary["mean_ci_high"]
    # The CI on the mean must be tighter than the raw outcome band.
    assert summary["mean_ci_high"] - summary["mean_ci_low"] < summary["p90"] - summary["p10"]


def test_summarize_delta_ci_collapses_for_constant_samples() -> None:
    summary = summarize_delta([2.0, 2.0, 2.0])
    assert summary["mean_ci_low"] == 2.0
    assert summary["mean_ci_high"] == 2.0


def test_summarize_delta_ci_narrows_with_more_samples() -> None:
    narrow = summarize_delta([1.0, -1.0] * 100)
    wide = summarize_delta([1.0, -1.0] * 4)
    assert narrow["mean_ci_high"] - narrow["mean_ci_low"] < wide["mean_ci_high"] - wide["mean_ci_low"]


def test_aggregate_window_deltas_sums_iteration_wise() -> None:
    aggregate = aggregate_window_deltas([[1.0, 2.0], [3.0, 4.0]])
    # Iteration totals are [4.0, 6.0], so the window mean is 5.0.
    assert aggregate["mean"] == 5.0
    assert aggregate["mean_ci_low"] < 5.0 < aggregate["mean_ci_high"]


def test_aggregate_window_deltas_rejects_mismatched_games() -> None:
    with pytest.raises(ValueError, match="same iteration count"):
        aggregate_window_deltas([[1.0, 2.0], [3.0]])


def test_aggregate_window_deltas_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty set of game deltas"):
        aggregate_window_deltas([])


def test_engine_collect_samples_is_deterministic_and_matches_summary() -> None:
    projections = [projection(0.03), projection(0.05), projection(0.02)]

    first = run_matchup_simulation(projections, iteration_count=50, seed=42, collect_samples=True)
    second = run_matchup_simulation(projections, iteration_count=50, seed=42, collect_samples=True)

    assert first["samples"]["runs_scored"] == second["samples"]["runs_scored"]
    assert first["samples"]["run_value"] == second["samples"]["run_value"]
    assert len(first["samples"]["runs_scored"]) == 50

    sample_mean = round(sum(first["samples"]["runs_scored"]) / 50, 4)
    assert first["runs_scored"]["mean"] == sample_mean


def test_engine_omits_samples_by_default() -> None:
    projections = [projection(0.03)]
    result = run_matchup_simulation(projections, iteration_count=10, seed=1)
    assert "samples" not in result


def test_common_random_numbers_isolate_an_upgraded_hitter() -> None:
    baseline_projections = [projection(0.02), projection(0.02), projection(0.02)]
    variant_projections = [projection(0.02), projection(0.25), projection(0.02)]

    seed = 7
    baseline = run_matchup_simulation(baseline_projections, iteration_count=300, seed=seed, collect_samples=True)
    variant = run_matchup_simulation(variant_projections, iteration_count=300, seed=seed, collect_samples=True)

    deltas = paired_delta_samples(
        baseline["samples"]["runs_scored"],
        variant["samples"]["runs_scored"],
    )
    summary = summarize_delta(deltas)
    # Swapping in a far better hitter must add runs on average.
    assert summary["mean"] > 0
