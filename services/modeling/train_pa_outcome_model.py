from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.modeling.baseline_utils import (
    calibration_bins,
    classification_metrics,
    feature_key,
    load_jsonl,
    split_rows_by_holdout_games,
    write_json,
)
from services.modeling.learned_damage import (
    build_damage_feature_map,
    fit_binary_logistic,
    fit_hit_type_models,
    predict_binary_probability,
    predict_hit_type_distribution,
)

OUTCOMES = ("walk", "strikeout", "single", "double", "triple", "home_run", "ball_in_play_out")
PA_STAGE_OUTCOMES = ("walk", "strikeout", "ball_in_play")
BIP_STAGE_OUTCOMES = ("hit", "ball_in_play_out")
HIT_TYPE_OUTCOMES = ("single", "double", "triple", "home_run")
OUTCOME_ALIAS_MAP = {
    "walk": "walk",
    "intent_walk": "walk",
    "hit_by_pitch": "walk",
    "catcher_interf": "walk",
    "strikeout": "strikeout",
    "strikeout_double_play": "strikeout",
    "single": "single",
    "double": "double",
    "triple": "triple",
    "home_run": "home_run",
    "field_out": "ball_in_play_out",
    "force_out": "ball_in_play_out",
    "grounded_into_double_play": "ball_in_play_out",
    "fielders_choice_out": "ball_in_play_out",
    "fielders_choice": "ball_in_play_out",
    "double_play": "ball_in_play_out",
    "triple_play": "ball_in_play_out",
    "sac_fly": "ball_in_play_out",
    "sac_bunt": "ball_in_play_out",
    "field_error": "ball_in_play_out",
}
OUTCOME_PRIOR_WEIGHTS = {
    "walk": 30,
    "strikeout": 30,
    "ball_in_play": 30,
    "hit": 35,
    "single": 30,
    "double": 45,
    "triple": 90,
    "home_run": 60,
    "ball_in_play_out": 30,
}


def map_pa_outcome(result: str | None) -> str | None:
    if not result:
        return None
    normalized = result.strip().lower()
    return OUTCOME_ALIAS_MAP.get(normalized)


def dominant_pitch_type(pitch_rows: list[dict[str, Any]]) -> str:
    counts = Counter(str(row.get("pitch_type") or "unknown") for row in pitch_rows)
    return counts.most_common(1)[0][0] if counts else "unknown"


def count_bucket_from_pitch(pitch_row: dict[str, Any]) -> str:
    balls = int(pitch_row.get("balls") or 0)
    strikes = int(pitch_row.get("strikes") or 0)
    if strikes >= 2:
        return "two_strike"
    if balls >= 3 and strikes < 2:
        return "hitter_ahead"
    if strikes > balls:
        return "pitcher_ahead"
    return "even"


def form_bucket_from_metrics(metrics: dict[str, Any] | None) -> str:
    if not metrics:
        return "unknown"
    strikeout_rate = float(metrics.get("strikeout_rate") or 0.0)
    walk_rate = float(metrics.get("walk_rate") or 0.0)
    hard_hit_rate = float(metrics.get("in_play_hard_hit_rate") or 0.0)

    if strikeout_rate >= 0.28 and walk_rate <= 0.08:
        return "bat-missing"
    if walk_rate >= 0.11:
        return "wild"
    if hard_hit_rate >= 0.45 and strikeout_rate <= 0.2:
        return "loud-contact"
    return "steady"


def hitter_profile_lookup(input_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    path = input_dir / "hitter_tendency_profiles.jsonl"
    if not path.exists():
        return {}

    profiles: dict[tuple[str, str], dict[str, Any]] = {}
    for row in load_jsonl(path):
        hitter_id = str(row.get("hitter_id") or "")
        split_key = str(row.get("split_key") or "")
        if hitter_id and split_key:
            profiles[(hitter_id, split_key)] = row
    return profiles


def latest_form_by_pitcher(input_dir: Path) -> dict[str, dict[str, Any]]:
    path = input_dir / "pitcher_form_windows.jsonl"
    if not path.exists():
        return {}

    latest: dict[str, dict[str, Any]] = {}
    for row in load_jsonl(path):
        pitcher_id = str(row["pitcher_id"])
        current = latest.get(pitcher_id)
        if current is None or str(row.get("window_end") or "") > str(current.get("window_end") or ""):
            latest[pitcher_id] = row
    return latest


def average_non_null(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 4)


def hitter_whiff_bucket(profile: dict[str, Any] | None, pitch_type: str) -> str:
    if not profile:
        return "unknown"
    profile_json = profile.get("profile_json") or {}
    recent_form = profile_json.get("recent_form") or {}
    recent_value = recent_form.get("whiff_rate")
    if isinstance(recent_value, (int, float)):
        value = float(recent_value)
    else:
        value = None
    by_pitch = (profile_json.get("whiff_rate_by_pitch_type") or {})
    if value is None:
        value = by_pitch.get(pitch_type)
    if value is None:
        value = average_non_null(
            [float(item) if isinstance(item, (int, float)) else None for item in by_pitch.values()]
        )
    if value is None:
        return "unknown"
    if value >= 0.32:
        return "swing_miss_prone"
    if value <= 0.18:
        return "contact_oriented"
    return "neutral"


def hitter_chase_bucket(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "unknown"
    profile_json = profile.get("profile_json") or {}
    recent_form = profile_json.get("recent_form") or {}
    chase_rate = recent_form.get("chase_rate")
    if not isinstance(chase_rate, (int, float)):
        chase_rate = profile_json.get("chase_rate")
    if not isinstance(chase_rate, (int, float)):
        return "unknown"
    if chase_rate >= 0.32:
        return "aggressive"
    if chase_rate <= 0.22:
        return "selective"
    return "neutral"


def pitcher_whiff_bucket(metrics: dict[str, Any] | None, pitch_type: str) -> str:
    if not metrics:
        return "unknown"
    whiff_by_pitch = (metrics.get("whiff_rate_by_pitch_type") or {})
    whiff_rate = whiff_by_pitch.get(pitch_type)
    if not isinstance(whiff_rate, (int, float)):
        overall_strikeout_rate = ((metrics.get("overall_metrics") or {}).get("strikeout_rate"))
        whiff_rate = overall_strikeout_rate if isinstance(overall_strikeout_rate, (int, float)) else None
    if whiff_rate is None:
        return "unknown"
    if whiff_rate >= 0.32:
        return "bat_missing"
    if whiff_rate <= 0.18:
        return "contact_manager"
    return "average"


def hitter_damage_bucket(profile: dict[str, Any] | None, pitch_type: str) -> str:
    if not profile:
        return "unknown"
    profile_json = profile.get("profile_json") or {}
    recent_form = profile_json.get("recent_form") or {}
    recent_damage = recent_form.get("hard_hit_rate")
    if isinstance(recent_damage, (int, float)):
        damage_rate = float(recent_damage)
    else:
        damage_by_pitch = profile_json.get("damage_rate_by_pitch_type") or {}
        damage_rate = damage_by_pitch.get(pitch_type)
        if not isinstance(damage_rate, (int, float)):
            damage_by_zone = profile_json.get("damage_rate_by_zone_bucket") or {}
            damage_rate = average_non_null(
                [float(item) if isinstance(item, (int, float)) else None for item in damage_by_zone.values()]
            )
    if damage_rate is None:
        return "unknown"
    if damage_rate >= 0.42:
        return "impact"
    if damage_rate <= 0.28:
        return "light"
    return "average"


def pitcher_contact_bucket(metrics: dict[str, Any] | None) -> str:
    if not metrics:
        return "unknown"
    overall_metrics = metrics.get("overall_metrics") or {}
    hard_hit_rate = overall_metrics.get("in_play_hard_hit_rate")
    if not isinstance(hard_hit_rate, (int, float)):
        return "unknown"
    if hard_hit_rate >= 0.42:
        return "loud_contact"
    if hard_hit_rate <= 0.3:
        return "suppresses_damage"
    return "average"


def hitter_air_bucket(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "unknown"
    recent_form = (profile.get("profile_json") or {}).get("recent_form") or {}
    air_ball_rate = recent_form.get("air_ball_rate")
    if not isinstance(air_ball_rate, (int, float)):
        return "unknown"
    if air_ball_rate >= 0.6:
        return "lifted"
    if air_ball_rate <= 0.38:
        return "ground_heavy"
    return "balanced"


def hitter_power_bucket(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "unknown"
    recent_form = (profile.get("profile_json") or {}).get("recent_form") or {}
    barrel_proxy_rate = recent_form.get("barrel_proxy_rate")
    if not isinstance(barrel_proxy_rate, (int, float)):
        return "unknown"
    if barrel_proxy_rate >= 0.14:
        return "impact"
    if barrel_proxy_rate <= 0.05:
        return "limited"
    return "average"


def launch_bucket(row: dict[str, Any]) -> str:
    launch_angle = row.get("launch_angle")
    if not isinstance(launch_angle, (int, float)):
        return "unknown"
    if launch_angle < 10:
        return "ground"
    if launch_angle <= 25:
        return "line"
    return "air"


def exit_velocity_bucket(row: dict[str, Any]) -> str:
    launch_speed = row.get("launch_speed")
    if not isinstance(launch_speed, (int, float)):
        return "unknown"
    if launch_speed >= 98:
        return "impact"
    if launch_speed >= 90:
        return "firm"
    return "soft"


def build_pa_training_rows(input_dir: Path) -> list[dict[str, Any]]:
    pa_rows = load_jsonl(input_dir / "plate_appearances.jsonl")
    pitch_rows = load_jsonl(input_dir / "pitches.jsonl")
    latest_forms = latest_form_by_pitcher(input_dir)
    hitter_profiles = hitter_profile_lookup(input_dir)
    pitches_by_pa: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pitch_rows:
        pitches_by_pa[str(row["pa_id"])].append(row)

    training_rows: list[dict[str, Any]] = []
    for pa_row in pa_rows:
        outcome = map_pa_outcome(pa_row.get("result"))
        pa_pitches = pitches_by_pa.get(str(pa_row["pa_id"]), [])
        if outcome is None or not pa_pitches:
            continue
        ordered_pitches = sorted(pa_pitches, key=lambda row: int(row.get("pitch_number") or 0))
        first_pitch = ordered_pitches[0]
        last_pitch = ordered_pitches[-1]
        latest_form = latest_forms.get(str(pa_row["pitcher_id"]))
        pitch_type = dominant_pitch_type(ordered_pitches)
        split_key = f"vs_{first_pitch.get('pitcher_hand') or 'UNK'}"
        hitter_profile = hitter_profiles.get((str(pa_row["hitter_id"]), split_key))
        form_profile_json = (latest_form or {}).get("profile_json") or {}
        training_rows.append(
            {
                "pa_id": pa_row["pa_id"],
                "game_id": pa_row["game_id"],
                "pitcher_id": pa_row["pitcher_id"],
                "hitter_id": pa_row["hitter_id"],
                "pitcher_hand": first_pitch.get("pitcher_hand") or "R",
                "hitter_side": first_pitch.get("hitter_side") or "R",
                "pitch_type": pitch_type,
                "count_bucket": count_bucket_from_pitch(last_pitch),
                "pitcher_form_bucket": form_bucket_from_metrics(form_profile_json.get("overall_metrics")),
                "pitcher_whiff_bucket": pitcher_whiff_bucket(form_profile_json, pitch_type),
                "pitcher_contact_bucket": pitcher_contact_bucket(form_profile_json),
                "pitcher_hard_hit_rate": float((form_profile_json.get("overall_metrics") or {}).get("in_play_hard_hit_rate") or 0.35),
                "pitcher_strikeout_rate": float((form_profile_json.get("overall_metrics") or {}).get("strikeout_rate") or 0.23),
                "pitcher_walk_rate": float((form_profile_json.get("overall_metrics") or {}).get("walk_rate") or 0.08),
                "hitter_whiff_bucket": hitter_whiff_bucket(hitter_profile, pitch_type),
                "hitter_chase_bucket": hitter_chase_bucket(hitter_profile),
                "hitter_damage_bucket": hitter_damage_bucket(hitter_profile, pitch_type),
                "hitter_air_bucket": hitter_air_bucket(hitter_profile),
                "hitter_power_bucket": hitter_power_bucket(hitter_profile),
                "hitter_recent_hard_hit_rate": float((((hitter_profile or {}).get("profile_json") or {}).get("recent_form") or {}).get("hard_hit_rate") or 0.35),
                "hitter_recent_air_ball_rate": float((((hitter_profile or {}).get("profile_json") or {}).get("recent_form") or {}).get("air_ball_rate") or 0.45),
                "hitter_recent_barrel_proxy_rate": float((((hitter_profile or {}).get("profile_json") or {}).get("recent_form") or {}).get("barrel_proxy_rate") or 0.08),
                "launch_bucket": launch_bucket(last_pitch),
                "exit_velocity_bucket": exit_velocity_bucket(last_pitch),
                "outcome": outcome,
            }
        )
    return training_rows


def resolve_combined_holdout_game_ids(input_dirs: list[Path], holdout_fraction: float) -> set[str]:
    if holdout_fraction <= 0:
        return set()

    ordered_games: list[dict[str, str]] = []
    for input_dir in input_dirs:
        games_path = input_dir / "games.jsonl"
        if not games_path.exists():
            continue
        for row in load_jsonl(games_path):
            game_id = str(row.get("game_id") or "")
            if game_id:
                ordered_games.append(
                    {
                        "game_id": game_id,
                        "game_date": str(row.get("game_date") or ""),
                    }
                )

    if not ordered_games:
        return set()

    ordered_games.sort(key=lambda row: (row["game_date"], row["game_id"]))
    holdout_count = max(1, round(len(ordered_games) * holdout_fraction))
    return {row["game_id"] for row in ordered_games[-holdout_count:]}


def smoothed_outcome_rates(
    counts: Counter[str],
    total: int,
    prior_rates: dict[str, float],
    outcomes: tuple[str, ...],
) -> dict[str, float]:
    smoothed = {
        outcome: (counts.get(outcome, 0) + (prior_rates[outcome] * OUTCOME_PRIOR_WEIGHTS[outcome]))
        / (total + OUTCOME_PRIOR_WEIGHTS[outcome])
        for outcome in outcomes
    }
    normalizer = sum(smoothed.values()) or 1.0
    return {outcome: round(value / normalizer, 4) for outcome, value in smoothed.items()}


def train_segment_outcome_rates(
    rows: list[dict[str, Any]],
    segments: dict[str, list[str]],
    outcome_field: str,
    outcomes: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    global_counts = Counter(str(row[outcome_field]) for row in rows)
    global_total = len(rows)
    global_rates = {outcome: global_counts.get(outcome, 0) / global_total for outcome in outcomes}

    outputs: dict[str, dict[str, Any]] = {}
    for segment_name, fields in segments.items():
        totals: Counter[str] = Counter()
        outcome_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            key = feature_key(row, fields)
            totals[key] += 1
            outcome_counts[key][str(row[outcome_field])] += 1

        outputs[segment_name] = {
            "fields": fields,
            "rates": {
                key: {
                    "sample_size": totals[key],
                    "outcome_rates": smoothed_outcome_rates(outcome_counts[key], totals[key], global_rates, outcomes),
                }
                for key in sorted(totals)
            },
        }
    return outputs


def _predict_stage_distribution(
    row: dict[str, Any],
    artifact: dict[str, Any],
    stage_name: str,
    outcome_rates_key: str = "outcome_rates",
) -> dict[str, float]:
    stage = artifact.get("stages", {}).get(stage_name, {})
    outcomes = stage.get("outcomes", [])
    if not outcomes:
        return {}

    global_rates = stage.get("global_rates", {})
    segment_specs = stage.get("segment_specs", {})
    distribution: dict[str, list[float]] = {
        outcome: [float(global_rates.get(outcome, 0.0))]
        for outcome in outcomes
    }
    for segment_name, fields in segment_specs.items():
        key = feature_key(row, fields)
        rate_info = stage.get("segments", {}).get(segment_name, {}).get("rates", {}).get(key)
        if not rate_info:
            continue
        for outcome, rate in rate_info.get(outcome_rates_key, {}).items():
            if outcome in distribution:
                distribution[outcome].append(float(rate))

    averaged = {outcome: round(sum(values) / len(values), 4) for outcome, values in distribution.items()}
    total = sum(averaged.values()) or 1.0
    return {outcome: round(value / total, 4) for outcome, value in averaged.items()}


def predict_outcome_distribution(row: dict[str, Any], artifact: dict[str, Any]) -> dict[str, float]:
    if artifact.get("stages"):
        pa_stage = _predict_stage_distribution(row, artifact, "pa_stage")
        bip_hit_stage = _predict_stage_distribution(row, artifact, "bip_hit_stage")
        hit_type_stage = _predict_stage_distribution(row, artifact, "hit_type_stage")
        learned_damage = artifact.get("learned_damage", {})
        if learned_damage:
            damage_features = build_damage_feature_map(row)
            if bip_hit_stage and learned_damage.get("bip_hit_model"):
                learned_hit_probability = predict_binary_probability(learned_damage["bip_hit_model"], damage_features)
                bip_hit_stage = {
                    "hit": round((bip_hit_stage.get("hit", 0.0) * 0.45) + (learned_hit_probability * 0.55), 4),
                    "ball_in_play_out": round((bip_hit_stage.get("ball_in_play_out", 0.0) * 0.45) + ((1.0 - learned_hit_probability) * 0.55), 4),
                }
            if hit_type_stage and learned_damage.get("hit_type_model"):
                learned_hit_types = predict_hit_type_distribution(learned_damage["hit_type_model"], damage_features)
                hit_type_stage = {
                    outcome: round((hit_type_stage.get(outcome, 0.0) * 0.4) + (learned_hit_types.get(outcome, 0.0) * 0.6), 4)
                    for outcome in hit_type_stage
                }
                total = sum(hit_type_stage.values()) or 1.0
                hit_type_stage = {outcome: round(value / total, 4) for outcome, value in hit_type_stage.items()}

        if pa_stage and bip_hit_stage and hit_type_stage:
            ball_in_play_rate = pa_stage.get("ball_in_play", 0.0)
            hit_rate = ball_in_play_rate * bip_hit_stage.get("hit", 0.0)
            bip_out_rate = ball_in_play_rate * bip_hit_stage.get("ball_in_play_out", 0.0)
            final_distribution = {
                "walk": round(pa_stage.get("walk", 0.0), 4),
                "strikeout": round(pa_stage.get("strikeout", 0.0), 4),
                "single": round(hit_rate * hit_type_stage.get("single", 0.0), 4),
                "double": round(hit_rate * hit_type_stage.get("double", 0.0), 4),
                "triple": round(hit_rate * hit_type_stage.get("triple", 0.0), 4),
                "home_run": round(hit_rate * hit_type_stage.get("home_run", 0.0), 4),
                "ball_in_play_out": round(bip_out_rate, 4),
            }
            total = sum(final_distribution.values()) or 1.0
            return {outcome: round(value / total, 4) for outcome, value in final_distribution.items()}

    segment_specs = {
        "by_pitch_type": ["pitch_type"],
        "by_matchup": ["pitcher_hand", "hitter_side"],
        "by_count": ["count_bucket"],
        "by_matchup_and_pitch": ["pitcher_hand", "hitter_side", "pitch_type"],
        "by_matchup_pitch_count": ["pitcher_hand", "hitter_side", "pitch_type", "count_bucket"],
        "by_form_and_pitch": ["pitcher_form_bucket", "pitch_type"],
        "by_whiff_buckets": ["pitcher_whiff_bucket", "hitter_whiff_bucket", "pitch_type"],
        "by_strikeout_context": ["count_bucket", "pitcher_whiff_bucket", "hitter_whiff_bucket"],
        "by_chase_context": ["hitter_chase_bucket", "pitcher_hand", "hitter_side"],
    }

    distribution: dict[str, list[float]] = {outcome: [float(artifact["global_outcome_rates"][outcome])] for outcome in OUTCOMES}
    for segment_name, fields in segment_specs.items():
        key = feature_key(row, fields)
        rate_info = artifact.get("segments", {}).get(segment_name, {}).get("rates", {}).get(key)
        if not rate_info:
            continue
        for outcome, rate in rate_info["outcome_rates"].items():
            distribution[outcome].append(float(rate))

    averaged = {outcome: round(sum(values) / len(values), 4) for outcome, values in distribution.items()}
    total = sum(averaged.values()) or 1.0
    return {outcome: round(value / total, 4) for outcome, value in averaged.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a lightweight direct PA outcome model artifact.")
    parser.add_argument(
        "--input-dir",
        action="append",
        help="Directory containing pitches.jsonl and plate_appearances.jsonl. Repeat to pool multiple windows.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/models/pa_outcome_model_v1.json",
        help="Path for the trained PA outcome artifact.",
    )
    parser.add_argument(
        "--holdout-fraction",
        type=float,
        default=0.2,
        help="Fraction of most recent games to reserve for holdout calibration.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dirs = [Path(path) for path in (args.input_dir or ["data/processed"])]
    pa_training_rows: list[dict[str, Any]] = []
    for input_dir in input_dirs:
        pa_training_rows.extend(build_pa_training_rows(input_dir))
    if not pa_training_rows:
        raise ValueError("No mapped plate appearance rows found for PA outcome training")

    holdout_game_ids = resolve_combined_holdout_game_ids(input_dirs, args.holdout_fraction)
    training_rows, holdout_rows = split_rows_by_holdout_games(pa_training_rows, holdout_game_ids)
    if not training_rows:
        training_rows = pa_training_rows
        holdout_rows = []

    pa_stage_rows = []
    for row in training_rows:
        stage_row = dict(row)
        stage_row["pa_outcome"] = "ball_in_play" if row["outcome"] not in {"walk", "strikeout"} else row["outcome"]
        pa_stage_rows.append(stage_row)
    bip_stage_rows = []
    for row in training_rows:
        if row["outcome"] in {"walk", "strikeout"}:
            continue
        stage_row = dict(row)
        stage_row["bip_outcome"] = "ball_in_play_out" if row["outcome"] == "ball_in_play_out" else "hit"
        bip_stage_rows.append(stage_row)
    hit_type_rows = [row for row in training_rows if row["outcome"] in HIT_TYPE_OUTCOMES]

    pa_segments = {
        "by_pitch_type": ["pitch_type"],
        "by_matchup": ["pitcher_hand", "hitter_side"],
        "by_count": ["count_bucket"],
        "by_matchup_and_pitch": ["pitcher_hand", "hitter_side", "pitch_type"],
        "by_matchup_pitch_count": ["pitcher_hand", "hitter_side", "pitch_type", "count_bucket"],
        "by_form_and_pitch": ["pitcher_form_bucket", "pitch_type"],
        "by_whiff_buckets": ["pitcher_whiff_bucket", "hitter_whiff_bucket", "pitch_type"],
        "by_strikeout_context": ["count_bucket", "pitcher_whiff_bucket", "hitter_whiff_bucket"],
        "by_chase_context": ["hitter_chase_bucket", "pitcher_hand", "hitter_side"],
    }
    bip_segments = {
        "by_pitch_type": ["pitch_type"],
        "by_matchup": ["pitcher_hand", "hitter_side"],
        "by_damage_context": ["pitcher_contact_bucket", "hitter_damage_bucket", "pitch_type"],
        "by_form_and_pitch": ["pitcher_form_bucket", "pitch_type"],
        "by_matchup_damage": ["pitcher_hand", "hitter_side", "pitcher_contact_bucket", "hitter_damage_bucket"],
    }
    hit_type_segments = {
        "by_pitch_type": ["pitch_type"],
        "by_matchup": ["pitcher_hand", "hitter_side"],
        "by_damage_context": ["pitcher_contact_bucket", "hitter_damage_bucket", "pitch_type"],
        "by_power_context": ["pitcher_hand", "hitter_side", "pitcher_contact_bucket", "hitter_damage_bucket"],
        "by_form_and_pitch": ["pitcher_form_bucket", "pitch_type"],
        "by_air_power": ["hitter_air_bucket", "hitter_power_bucket", "pitch_type"],
        "by_contact_quality": ["launch_bucket", "exit_velocity_bucket"],
    }
    global_counts = Counter(str(row["outcome"]) for row in training_rows)
    global_total = len(training_rows)
    global_outcome_rates = {
        outcome: round(global_counts.get(outcome, 0) / global_total, 4) for outcome in OUTCOMES
    }
    pa_stage_counts = Counter(str(row["pa_outcome"]) for row in pa_stage_rows)
    pa_stage_total = len(pa_stage_rows)
    pa_stage_global_rates = {
        outcome: round(pa_stage_counts.get(outcome, 0) / pa_stage_total, 4) for outcome in PA_STAGE_OUTCOMES
    }
    bip_stage_counts = Counter(str(row["bip_outcome"]) for row in bip_stage_rows)
    bip_stage_total = len(bip_stage_rows) or 1
    bip_stage_global_rates = {
        outcome: round(bip_stage_counts.get(outcome, 0) / bip_stage_total, 4) for outcome in BIP_STAGE_OUTCOMES
    }
    hit_type_counts = Counter(str(row["outcome"]) for row in hit_type_rows)
    hit_type_total = len(hit_type_rows) or 1
    hit_type_global_rates = {
        outcome: round(hit_type_counts.get(outcome, 0) / hit_type_total, 4) for outcome in HIT_TYPE_OUTCOMES
    }

    artifact = {
        "model_name": "pa_outcome_model_v1",
        "model_type": "staged_frequency_baseline",
        "training_row_count": len(training_rows),
        "holdout_row_count": len(holdout_rows),
        "outcomes": list(OUTCOMES),
        "global_outcome_rates": global_outcome_rates,
        "stages": {
            "pa_stage": {
                "outcomes": list(PA_STAGE_OUTCOMES),
                "global_rates": pa_stage_global_rates,
                "segment_specs": pa_segments,
                "segments": train_segment_outcome_rates(
                    pa_stage_rows,
                    pa_segments,
                    outcome_field="pa_outcome",
                    outcomes=PA_STAGE_OUTCOMES,
                ),
            },
            "bip_hit_stage": {
                "outcomes": list(BIP_STAGE_OUTCOMES),
                "global_rates": bip_stage_global_rates,
                "segment_specs": bip_segments,
                "segments": train_segment_outcome_rates(
                    bip_stage_rows,
                    bip_segments,
                    outcome_field="bip_outcome",
                    outcomes=BIP_STAGE_OUTCOMES,
                ) if bip_stage_rows else {},
            },
            "hit_type_stage": {
                "outcomes": list(HIT_TYPE_OUTCOMES),
                "global_rates": hit_type_global_rates,
                "segment_specs": hit_type_segments,
                "segments": train_segment_outcome_rates(
                    hit_type_rows,
                    hit_type_segments,
                    outcome_field="outcome",
                    outcomes=HIT_TYPE_OUTCOMES,
                ) if hit_type_rows else {},
            },
        },
    }
    if bip_stage_rows:
        bip_features = [build_damage_feature_map(row) for row in bip_stage_rows]
        bip_labels = [1 if row["bip_outcome"] == "hit" else 0 for row in bip_stage_rows]
        artifact["learned_damage"] = {
            "bip_hit_model": fit_binary_logistic(bip_features, bip_labels),
            "hit_type_model": fit_hit_type_models(
                [build_damage_feature_map(row) for row in hit_type_rows],
                [str(row["outcome"]) for row in hit_type_rows],
            ) if hit_type_rows else {},
        }

    calibration: dict[str, Any] = {}
    for outcome in OUTCOMES:
        if holdout_rows:
            predictions = [predict_outcome_distribution(row, artifact)[outcome] for row in holdout_rows]
            labels = [1 if row["outcome"] == outcome else 0 for row in holdout_rows]
            calibration[outcome] = {
                **classification_metrics(predictions, labels),
                "holdout_game_count": len(holdout_game_ids),
                "bin_report": calibration_bins(predictions, labels),
            }
        else:
            calibration[outcome] = {
                **classification_metrics([], []),
                "holdout_game_count": 0,
                "bin_report": [],
            }
    artifact["calibration"] = calibration

    write_json(Path(args.output), artifact)
    print(f"Wrote PA outcome model artifact to {args.output}")


if __name__ == "__main__":
    main()
