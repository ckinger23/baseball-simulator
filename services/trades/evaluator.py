"""Pure comparison math for trade evaluation.

Baseline and variant lineups are simulated with common random numbers (the
same seed per game), so subtracting per-iteration samples yields a paired
delta distribution with far less noise than differencing two independent
summaries.
"""

from __future__ import annotations

import math
from typing import Any

from services.simulation.engine import summarize_metric

# Two-sided 90% normal confidence multiplier for the standard error of the mean.
CONFIDENCE_Z_90 = 1.645


def build_variant_lineup(
    lineup: list[dict[str, Any]],
    displaced_hitter_id: str,
    incoming_hitter: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the lineup with the incoming hitter in the displaced hitter's spot."""
    lineup_ids = [str(hitter["hitter_id"]) for hitter in lineup]
    if str(incoming_hitter["hitter_id"]) in lineup_ids:
        raise ValueError(
            f"Incoming hitter {incoming_hitter['hitter_id']} is already in the projected lineup."
        )
    if displaced_hitter_id not in lineup_ids:
        raise ValueError(
            f"Displaced hitter {displaced_hitter_id} is not in the projected lineup."
        )

    variant: list[dict[str, Any]] = []
    for hitter in lineup:
        if str(hitter["hitter_id"]) == displaced_hitter_id:
            variant.append(
                {
                    "hitter_id": str(incoming_hitter["hitter_id"]),
                    "hitter_name": str(incoming_hitter["hitter_name"]),
                    "batting_side": str(incoming_hitter.get("batting_side") or "R"),
                    "lineup_spot": hitter["lineup_spot"],
                }
            )
        else:
            variant.append(dict(hitter))
    return variant


def paired_delta_samples(
    baseline_samples: list[float],
    variant_samples: list[float],
) -> list[float]:
    """Per-iteration variant-minus-baseline deltas from same-seed simulations."""
    if len(baseline_samples) != len(variant_samples):
        raise ValueError(
            "Baseline and variant simulations must use the same iteration count "
            f"({len(baseline_samples)} vs {len(variant_samples)})."
        )
    if not baseline_samples:
        raise ValueError("Cannot compute deltas from empty simulation samples.")
    return [variant - baseline for baseline, variant in zip(baseline_samples, variant_samples)]


def summarize_delta(delta_samples: list[float]) -> dict[str, float]:
    """Summarize a paired delta distribution.

    The p10/p50/p90 band describes single-outcome variability (how different one
    simulated game can look), while mean_ci_low/mean_ci_high is a 90% confidence
    interval on the mean delta itself — the band that says whether the swap's
    average effect is distinguishable from zero.
    """
    summary = summarize_metric(delta_samples)
    sample_count = len(delta_samples)
    mean = sum(delta_samples) / sample_count
    variance = sum((value - mean) ** 2 for value in delta_samples) / max(sample_count - 1, 1)
    standard_error = math.sqrt(variance / sample_count)
    summary["mean_ci_low"] = round(mean - CONFIDENCE_Z_90 * standard_error, 4)
    summary["mean_ci_high"] = round(mean + CONFIDENCE_Z_90 * standard_error, 4)
    return summary


def aggregate_window_deltas(per_game_delta_samples: list[list[float]]) -> dict[str, float]:
    """Sum paired deltas across games iteration-wise to get the window-total delta distribution."""
    if not per_game_delta_samples:
        raise ValueError("Cannot aggregate an empty set of game deltas.")
    iteration_counts = {len(samples) for samples in per_game_delta_samples}
    if len(iteration_counts) != 1:
        raise ValueError("All games must be simulated with the same iteration count to aggregate.")

    totals = [sum(iteration) for iteration in zip(*per_game_delta_samples)]
    return summarize_delta(totals)
