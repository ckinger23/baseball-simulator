from __future__ import annotations

import math
import random
from typing import Any


DEFAULT_RELIEVER_ENTRY_BATTER_NUMBER = 19
RunnerState = str | None


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    index = (len(ordered) - 1) * pct
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return round(ordered[int(index)], 4)
    weight = index - lower
    value = ordered[lower] * (1 - weight) + ordered[upper] * weight
    return round(value, 4)


def summarize_metric(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p10": 0.0, "p50": 0.0, "p90": 0.0}
    return {
        "mean": round(sum(values) / len(values), 4),
        "p10": percentile(values, 0.10),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
    }


def force_walk_bases(bases: list[RunnerState], current_pitcher_role: str) -> list[str]:
    scored_runners: list[str] = []
    first, second, third = bases
    if not first:
        bases[0] = current_pitcher_role
        return scored_runners
    if first and not second:
        bases[1] = first
        bases[0] = current_pitcher_role
        return scored_runners
    if first and second and not third:
        bases[2] = second
        bases[1] = first
        bases[0] = current_pitcher_role
        return scored_runners
    if third:
        scored_runners.append(third)
    bases[2] = second
    bases[1] = first
    bases[0] = current_pitcher_role
    return scored_runners


def advance_on_single(
    rng: random.Random,
    bases: list[RunnerState],
    current_pitcher_role: str,
) -> list[str]:
    scored_runners: list[str] = [bases[2]] if bases[2] else []
    runner_from_second_scores = bool(bases[1]) and rng.random() < 0.62
    new_third = bases[1] if bases[1] and not runner_from_second_scores else None
    if new_third is None and bases[0] and rng.random() < 0.35:
        new_third = bases[0]
    new_second = bases[0] if bases[0] and new_third != bases[0] else None
    if runner_from_second_scores and bases[1]:
        scored_runners.append(bases[1])
    bases[2] = new_third
    bases[1] = new_second
    bases[0] = current_pitcher_role
    return [runner for runner in scored_runners if runner]


def advance_on_double(
    rng: random.Random,
    bases: list[RunnerState],
    current_pitcher_role: str,
) -> list[str]:
    scored_runners: list[str] = [runner for runner in (bases[2], bases[1]) if runner]
    runner_from_first_scores = bool(bases[0]) and rng.random() < 0.58
    if runner_from_first_scores and bases[0]:
        scored_runners.append(bases[0])
    bases[2] = bases[0] if bases[0] and not runner_from_first_scores else None
    bases[1] = current_pitcher_role
    bases[0] = None
    return scored_runners


def advance_on_triple(bases: list[RunnerState], current_pitcher_role: str) -> list[str]:
    scored_runners = [runner for runner in bases if runner]
    bases[0] = None
    bases[1] = None
    bases[2] = current_pitcher_role
    return scored_runners


def advance_on_homer(bases: list[RunnerState], current_pitcher_role: str) -> list[str]:
    scored_runners = [current_pitcher_role, *[runner for runner in bases if runner]]
    bases[0] = None
    bases[1] = None
    bases[2] = None
    return scored_runners


def handle_ball_in_play_out(
    rng: random.Random,
    bases: list[RunnerState],
    outs: int,
) -> tuple[list[str], int]:
    scored_runners: list[str] = []
    outs_added = 1

    if outs < 2 and bases[2] and rng.random() < 0.12:
        scored_runners.append(bases[2])
        bases[2] = None

    if outs < 2 and bases[0] and rng.random() < 0.09:
        bases[0] = None
        if bases[1]:
            bases[2] = bases[1]
        bases[1] = None
        outs_added = 2

    return scored_runners, outs_added


def draw_plate_appearance_outcome(rng: random.Random, projection: dict[str, Any]) -> str:
    ordered_outcomes = [
        ("walk", float(projection["estimated_bb_rate"])),
        ("strikeout", float(projection["estimated_k_rate"])),
        ("single", float(projection["single_rate"])),
        ("double", float(projection["double_rate"])),
        ("triple", float(projection["triple_rate"])),
        ("home_run", float(projection["home_run_rate"])),
    ]
    draw = rng.random()
    cumulative = 0.0
    for outcome, probability in ordered_outcomes:
        cumulative += probability
        if draw < cumulative:
            return outcome
    return "ball_in_play_out"


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normalize_projection_outcomes(projection: dict[str, Any]) -> dict[str, Any]:
    outcome_keys = [
        "estimated_bb_rate",
        "estimated_k_rate",
        "single_rate",
        "double_rate",
        "triple_rate",
        "home_run_rate",
        "out_in_play_rate",
    ]
    total = sum(float(projection[key]) for key in outcome_keys)
    if total <= 0:
        return projection

    normalized = dict(projection)
    for key in outcome_keys:
        normalized[key] = round(float(projection[key]) / total, 4)
    return normalized


def adjusted_projection_for_context(
    projection: dict[str, Any],
    times_through_order: int,
    pitcher_role: str,
) -> dict[str, Any]:
    adjusted = dict(projection)
    if pitcher_role == "starter":
        k_multiplier = 1.0 - (0.03 * max(times_through_order - 1, 0))
        walk_multiplier = 1.0 + (0.04 * max(times_through_order - 1, 0))
        contact_multiplier = 1.0 + (0.035 * max(times_through_order - 1, 0))
    else:
        k_multiplier = 1.04
        walk_multiplier = 0.97
        contact_multiplier = 0.95

    adjusted["estimated_k_rate"] = round(clamp(float(projection["estimated_k_rate"]) * k_multiplier, 0.01, 0.6), 4)
    adjusted["estimated_bb_rate"] = round(clamp(float(projection["estimated_bb_rate"]) * walk_multiplier, 0.01, 0.3), 4)
    for key in ("single_rate", "double_rate", "triple_rate", "home_run_rate", "out_in_play_rate"):
        adjusted[key] = round(clamp(float(projection[key]) * contact_multiplier, 0.0, 0.95), 4)

    hard_hit_rate = float(projection["hard_hit_rate_on_contact"])
    hard_hit_multiplier = 1.0 + (0.05 * max(times_through_order - 1, 0)) if pitcher_role == "starter" else 0.95
    adjusted["hard_hit_rate_on_contact"] = round(clamp(hard_hit_rate * hard_hit_multiplier, 0.05, 0.85), 4)
    return normalize_projection_outcomes(adjusted)


def run_matchup_simulation(
    hitter_projections: list[dict[str, Any]],
    iteration_count: int = 500,
    seed: int | None = None,
    innings: int = 9,
    reliever_hitter_projections: list[dict[str, Any]] | None = None,
    reliever_entry_batter_number: int | None = None,
    reliever_entry_inning: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    runs_scored: list[float] = []
    hits: list[float] = []
    home_runs: list[float] = []
    plate_appearances: list[float] = []
    strikeouts: list[float] = []
    walks: list[float] = []
    balls_in_play: list[float] = []
    hard_hit_balls: list[float] = []
    reliever_inherited_runners: list[float] = []
    reliever_inherited_runners_scored: list[float] = []
    run_values: list[float] = []

    for _ in range(iteration_count):
        lineup_index = 0
        bases: list[RunnerState] = [None, None, None]
        runs_total = 0
        hits_total = 0
        home_run_total = 0
        pa_total = 0
        k_total = 0
        bb_total = 0
        bip_total = 0
        hh_total = 0
        reliever_entered = False
        inherited_runners_total = 0
        inherited_runners_scored_total = 0
        run_total = 0.0

        for inning_number in range(1, innings + 1):
            outs = 0
            bases = [None, None, None]
            while outs < 3:
                batter_number = pa_total + 1
                reliever_triggered_by_batter = batter_number >= (
                    reliever_entry_batter_number or DEFAULT_RELIEVER_ENTRY_BATTER_NUMBER
                )
                reliever_triggered_by_inning = reliever_entry_inning is not None and inning_number >= reliever_entry_inning
                using_reliever = bool(reliever_hitter_projections) and (
                    reliever_triggered_by_batter or reliever_triggered_by_inning
                )
                if using_reliever and not reliever_entered:
                    reliever_entered = True
                    inherited_runners_total = sum(1 for runner in bases if runner == "starter")
                active_projections = reliever_hitter_projections if using_reliever else hitter_projections
                projection = active_projections[lineup_index % len(active_projections)]
                times_through_order = max(1, ((lineup_index // len(active_projections)) + 1))
                current_pitcher_role = "reliever" if using_reliever else "starter"
                context_projection = adjusted_projection_for_context(
                    projection=projection,
                    times_through_order=times_through_order,
                    pitcher_role=current_pitcher_role,
                )
                lineup_index += 1
                pa_total += 1

                outcome = draw_plate_appearance_outcome(rng, context_projection)
                hard_hit_rate = float(context_projection["hard_hit_rate_on_contact"])

                if outcome == "walk":
                    bb_total += 1
                    scored_runners = force_walk_bases(bases, current_pitcher_role)
                    runs_total += len(scored_runners)
                    inherited_runners_scored_total += sum(
                        1 for runner in scored_runners if reliever_entered and runner == "starter"
                    )
                    run_total += 0.33 + (len(scored_runners) * 0.95)
                    continue

                if outcome == "strikeout":
                    k_total += 1
                    outs += 1
                    run_total -= 0.27
                    continue

                bip_total += 1

                if outcome == "single":
                    hits_total += 1
                    hh_total += 1 if rng.random() < hard_hit_rate * 0.45 else 0
                    scored_runners = advance_on_single(rng, bases, current_pitcher_role)
                    runs_total += len(scored_runners)
                    inherited_runners_scored_total += sum(
                        1 for runner in scored_runners if reliever_entered and runner == "starter"
                    )
                    run_total += 0.47 + (len(scored_runners) * 0.9)
                    continue

                if outcome == "double":
                    hits_total += 1
                    hh_total += 1 if rng.random() < hard_hit_rate * 0.7 else 0
                    scored_runners = advance_on_double(rng, bases, current_pitcher_role)
                    runs_total += len(scored_runners)
                    inherited_runners_scored_total += sum(
                        1 for runner in scored_runners if reliever_entered and runner == "starter"
                    )
                    run_total += 0.77 + (len(scored_runners) * 0.95)
                    continue

                if outcome == "triple":
                    hits_total += 1
                    hh_total += 1
                    scored_runners = advance_on_triple(bases, current_pitcher_role)
                    runs_total += len(scored_runners)
                    inherited_runners_scored_total += sum(
                        1 for runner in scored_runners if reliever_entered and runner == "starter"
                    )
                    run_total += 1.05 + (len(scored_runners) * 0.98)
                    continue

                if outcome == "home_run":
                    hits_total += 1
                    home_run_total += 1
                    hh_total += 1
                    scored_runners = advance_on_homer(bases, current_pitcher_role)
                    runs_total += len(scored_runners)
                    inherited_runners_scored_total += sum(
                        1 for runner in scored_runners if reliever_entered and runner == "starter"
                    )
                    run_total += 1.4 + (len(scored_runners) * 1.02)
                    continue

                scored_runners, outs_added = handle_ball_in_play_out(rng, bases, outs)
                outs += outs_added
                runs_total += len(scored_runners)
                inherited_runners_scored_total += sum(
                    1 for runner in scored_runners if reliever_entered and runner == "starter"
                )
                run_total += 0.03 + (len(scored_runners) * 0.85)

        runs_scored.append(float(runs_total))
        hits.append(float(hits_total))
        home_runs.append(float(home_run_total))
        plate_appearances.append(float(pa_total))
        strikeouts.append(float(k_total))
        walks.append(float(bb_total))
        balls_in_play.append(float(bip_total))
        hard_hit_balls.append(float(hh_total))
        reliever_inherited_runners.append(float(inherited_runners_total))
        reliever_inherited_runners_scored.append(float(inherited_runners_scored_total))
        run_values.append(round(run_total, 4))

    return {
        "iteration_count": iteration_count,
        "runs_scored": summarize_metric(runs_scored),
        "hits": summarize_metric(hits),
        "home_runs": summarize_metric(home_runs),
        "plate_appearances": summarize_metric(plate_appearances),
        "strikeouts": summarize_metric(strikeouts),
        "walks": summarize_metric(walks),
        "balls_in_play": summarize_metric(balls_in_play),
        "hard_hit_balls": summarize_metric(hard_hit_balls),
        "reliever_inherited_runners": summarize_metric(reliever_inherited_runners),
        "reliever_inherited_runners_scored": summarize_metric(reliever_inherited_runners_scored),
        "run_value": summarize_metric(run_values),
    }
