from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from services.modeling.learned_damage import build_damage_feature_map, predict_binary_probability, predict_hit_type_distribution


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SWING_MODEL_PATH = PROJECT_ROOT / "artifacts/models/swing_model_v1.json"
DEFAULT_CONTACT_MODEL_PATH = PROJECT_ROOT / "artifacts/models/contact_model_v1.json"
DEFAULT_PA_OUTCOME_MODEL_PATH = PROJECT_ROOT / "artifacts/models/pa_outcome_model_v1.json"


@dataclass(frozen=True)
class BaselineArtifacts:
    swing: dict[str, Any]
    contact: dict[str, Any]
    pa_outcomes: dict[str, Any] | None = None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_baseline_artifacts() -> BaselineArtifacts | None:
    swing = _load_json(DEFAULT_SWING_MODEL_PATH)
    contact = _load_json(DEFAULT_CONTACT_MODEL_PATH)
    if swing is None or contact is None:
        return None
    pa_outcomes = _load_json(DEFAULT_PA_OUTCOME_MODEL_PATH)
    return BaselineArtifacts(swing=swing, contact=contact, pa_outcomes=pa_outcomes)


def dominant_pitch_type(
    form_profile: dict[str, Any] | None,
    manual_pitch_mix_adjustments: dict[str, float],
) -> str:
    if manual_pitch_mix_adjustments:
        return max(
            manual_pitch_mix_adjustments.items(),
            key=lambda item: item[1],
        )[0].lower()

    pitch_usage = ((form_profile or {}).get("profile_json") or {}).get("pitch_usage", {})
    if pitch_usage:
        return max(pitch_usage.items(), key=lambda item: item[1])[0]
    return "ff"


def lookup_segment_rate(
    artifact: dict[str, Any],
    segment_name: str,
    key: str,
    default_rate: float,
    artifact_root: str = "segments",
) -> float:
    rates = artifact.get(artifact_root, {}).get(segment_name, {}).get("rates", {})
    if key in rates:
        return float(rates[key]["positive_rate"])

    return default_rate


def _safe_nested_mean(values: list[float | None], fallback: float) -> float:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return fallback
    return round(sum(filtered) / len(filtered), 4)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _calibration_multiplier(payload: dict[str, Any] | None, key: str | None = None) -> float:
    if not payload:
        return 1.0
    if key is None:
        value = payload.get("global_multiplier")
    else:
        value = payload.get(key, {}).get("global_multiplier")
    if not isinstance(value, (int, float)) or value <= 0:
        return 1.0
    return float(value)


def _normalize_contact_rates(whiff_rate: float, in_play_rate: float) -> tuple[float, float]:
    max_total = 0.92
    total = whiff_rate + in_play_rate
    if total <= max_total:
        return round(whiff_rate, 4), round(in_play_rate, 4)
    scale = max_total / total
    return round(whiff_rate * scale, 4), round(in_play_rate * scale, 4)


def _normalize_outcome_distribution(distribution: dict[str, float]) -> dict[str, float]:
    cleaned = {key: max(0.0, value) for key, value in distribution.items()}
    total = sum(cleaned.values()) or 1.0
    return {key: round(value / total, 4) for key, value in cleaned.items()}


def _count_bucket_for_projection(
    form_profile: dict[str, Any] | None,
    manual_pitch_mix_adjustments: dict[str, float],
) -> str:
    if manual_pitch_mix_adjustments:
        max_pitch_share = max(manual_pitch_mix_adjustments.values(), default=0.0)
        if max_pitch_share >= 0.6:
            return "pitcher_ahead"

    metrics = ((form_profile or {}).get("profile_json") or {}).get("overall_metrics", {})
    strikeout_rate = float(metrics.get("strikeout_rate") or 0.0)
    walk_rate = float(metrics.get("walk_rate") or 0.0)
    if strikeout_rate >= 0.28:
        return "two_strike"
    if walk_rate >= 0.11:
        return "hitter_ahead"
    return "even"


def _form_bucket_for_projection(form_profile: dict[str, Any] | None) -> str:
    metrics = ((form_profile or {}).get("profile_json") or {}).get("overall_metrics", {})
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


def _average_non_null(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return round(sum(filtered) / len(filtered), 4)


def _hitter_whiff_bucket_for_projection(
    hitter_profile: dict[str, Any] | None,
    pitch_type: str,
) -> str:
    if not hitter_profile:
        return "unknown"
    profile_json = hitter_profile.get("profile_json") or {}
    recent_form = profile_json.get("recent_form") or {}
    recent_value = recent_form.get("whiff_rate")
    value = float(recent_value) if isinstance(recent_value, (int, float)) else None
    by_pitch = (profile_json.get("whiff_rate_by_pitch_type") or {})
    if value is None:
        value = by_pitch.get(pitch_type)
    if not isinstance(value, (int, float)):
        value = _average_non_null(
            [float(item) if isinstance(item, (int, float)) else None for item in by_pitch.values()]
        )
    if value is None:
        return "unknown"
    if value >= 0.32:
        return "swing_miss_prone"
    if value <= 0.18:
        return "contact_oriented"
    return "neutral"


def _hitter_chase_bucket_for_projection(hitter_profile: dict[str, Any] | None) -> str:
    if not hitter_profile:
        return "unknown"
    profile_json = hitter_profile.get("profile_json") or {}
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


def _pitcher_whiff_bucket_for_projection(
    form_profile: dict[str, Any] | None,
    pitch_type: str,
) -> str:
    profile_json = (form_profile or {}).get("profile_json") or {}
    whiff_by_pitch = profile_json.get("whiff_rate_by_pitch_type") or {}
    whiff_rate = whiff_by_pitch.get(pitch_type)
    if not isinstance(whiff_rate, (int, float)):
        overall_metrics = profile_json.get("overall_metrics") or {}
        strikeout_rate = overall_metrics.get("strikeout_rate")
        whiff_rate = strikeout_rate if isinstance(strikeout_rate, (int, float)) else None
    if whiff_rate is None:
        return "unknown"
    if whiff_rate >= 0.32:
        return "bat_missing"
    if whiff_rate <= 0.18:
        return "contact_manager"
    return "average"


def _hitter_damage_bucket_for_projection(
    hitter_profile: dict[str, Any] | None,
    pitch_type: str,
) -> str:
    if not hitter_profile:
        return "unknown"
    profile_json = hitter_profile.get("profile_json") or {}
    recent_form = profile_json.get("recent_form") or {}
    recent_damage = recent_form.get("hard_hit_rate")
    damage_rate = float(recent_damage) if isinstance(recent_damage, (int, float)) else None
    if damage_rate is None:
        by_pitch = profile_json.get("damage_rate_by_pitch_type") or {}
        damage_rate = by_pitch.get(pitch_type)
    if not isinstance(damage_rate, (int, float)):
        by_zone = profile_json.get("damage_rate_by_zone_bucket") or {}
        damage_rate = _average_non_null(
            [float(item) if isinstance(item, (int, float)) else None for item in by_zone.values()]
        )
    if damage_rate is None:
        return "unknown"
    if damage_rate >= 0.42:
        return "impact"
    if damage_rate <= 0.28:
        return "light"
    return "average"


def _pitcher_contact_bucket_for_projection(form_profile: dict[str, Any] | None) -> str:
    overall_metrics = ((form_profile or {}).get("profile_json") or {}).get("overall_metrics", {})
    hard_hit_rate = overall_metrics.get("in_play_hard_hit_rate")
    if not isinstance(hard_hit_rate, (int, float)):
        return "unknown"
    if hard_hit_rate >= 0.42:
        return "loud_contact"
    if hard_hit_rate <= 0.3:
        return "suppresses_damage"
    return "average"


def _hitter_air_bucket_for_projection(hitter_profile: dict[str, Any] | None) -> str:
    if not hitter_profile:
        return "unknown"
    recent_form = ((hitter_profile.get("profile_json") or {}).get("recent_form") or {})
    air_ball_rate = recent_form.get("air_ball_rate")
    if not isinstance(air_ball_rate, (int, float)):
        return "unknown"
    if air_ball_rate >= 0.6:
        return "lifted"
    if air_ball_rate <= 0.38:
        return "ground_heavy"
    return "balanced"


def _hitter_power_bucket_for_projection(hitter_profile: dict[str, Any] | None) -> str:
    if not hitter_profile:
        return "unknown"
    recent_form = ((hitter_profile.get("profile_json") or {}).get("recent_form") or {})
    barrel_proxy_rate = recent_form.get("barrel_proxy_rate")
    if not isinstance(barrel_proxy_rate, (int, float)):
        return "unknown"
    if barrel_proxy_rate >= 0.14:
        return "impact"
    if barrel_proxy_rate <= 0.05:
        return "limited"
    return "average"


def _projected_contact_quality_buckets(
    hitter_profile: dict[str, Any] | None,
    form_profile: dict[str, Any] | None,
) -> tuple[str, str]:
    hitter_recent = ((hitter_profile or {}).get("profile_json") or {}).get("recent_form", {})
    pitcher_metrics = ((form_profile or {}).get("profile_json") or {}).get("overall_metrics", {})
    hard_hit_rate = hitter_recent.get("hard_hit_rate")
    pitcher_hard_hit_rate = pitcher_metrics.get("in_play_hard_hit_rate")
    signals = [value for value in (hard_hit_rate, pitcher_hard_hit_rate) if isinstance(value, (int, float))]
    combined_hard_hit = (sum(float(value) for value in signals) / len(signals)) if signals else 0.35
    air_ball_rate = hitter_recent.get("air_ball_rate")

    if combined_hard_hit >= 0.44:
        exit_bucket = "impact"
    elif combined_hard_hit >= 0.34:
        exit_bucket = "firm"
    else:
        exit_bucket = "soft"

    if isinstance(air_ball_rate, (int, float)):
        if air_ball_rate >= 0.58:
            launch_bucket = "air"
        elif air_ball_rate >= 0.42:
            launch_bucket = "line"
        else:
            launch_bucket = "ground"
    else:
        launch_bucket = "unknown"

    return launch_bucket, exit_bucket


def _lookup_pa_outcome_distribution(
    artifact: dict[str, Any],
    pitcher_hand: str,
    hitter_side: str,
    pitch_type: str,
    count_bucket: str,
    pitcher_form_bucket: str,
    pitcher_whiff_bucket: str,
    hitter_whiff_bucket: str,
    hitter_chase_bucket: str,
    pitcher_contact_bucket: str,
    hitter_damage_bucket: str,
    hitter_air_bucket: str,
    hitter_power_bucket: str,
    launch_bucket: str,
    exit_velocity_bucket: str,
) -> dict[str, float]:
    if artifact.get("stages"):
        pa_stage = artifact.get("stages", {}).get("pa_stage", {})
        bip_hit_stage = artifact.get("stages", {}).get("bip_hit_stage", {})
        hit_type_stage = artifact.get("stages", {}).get("hit_type_stage", {})
        damage_stage = artifact.get("stages", {}).get("damage_stage", {})

        def lookup_stage(stage: dict[str, Any], parts_by_segment: dict[str, list[str]]) -> dict[str, float]:
            outcomes = stage.get("outcomes", [])
            if not outcomes:
                return {}
            collected = {
                outcome: [float(stage.get("global_rates", {}).get(outcome, 0.0))]
                for outcome in outcomes
            }
            for segment_name, parts in parts_by_segment.items():
                key = "|".join(parts)
                segment = stage.get("segments", {}).get(segment_name, {}).get("rates", {}).get(key)
                if not segment:
                    continue
                for outcome, value in segment.get("outcome_rates", {}).items():
                    if outcome in collected:
                        collected[outcome].append(float(value))
            averaged = {outcome: sum(values) / len(values) for outcome, values in collected.items()}
            return _normalize_outcome_distribution(averaged)

        pa_stage_distribution = lookup_stage(
            pa_stage,
            {
                "by_pitch_type": [f"pitch_type={pitch_type}"],
                "by_matchup": [f"pitcher_hand={pitcher_hand}", f"hitter_side={hitter_side}"],
                "by_count": [f"count_bucket={count_bucket}"],
                "by_matchup_and_pitch": [
                    f"pitcher_hand={pitcher_hand}",
                    f"hitter_side={hitter_side}",
                    f"pitch_type={pitch_type}",
                ],
                "by_matchup_pitch_count": [
                    f"pitcher_hand={pitcher_hand}",
                    f"hitter_side={hitter_side}",
                    f"pitch_type={pitch_type}",
                    f"count_bucket={count_bucket}",
                ],
                "by_form_and_pitch": [f"pitcher_form_bucket={pitcher_form_bucket}", f"pitch_type={pitch_type}"],
                "by_whiff_buckets": [
                    f"pitcher_whiff_bucket={pitcher_whiff_bucket}",
                    f"hitter_whiff_bucket={hitter_whiff_bucket}",
                    f"pitch_type={pitch_type}",
                ],
                "by_strikeout_context": [
                    f"count_bucket={count_bucket}",
                    f"pitcher_whiff_bucket={pitcher_whiff_bucket}",
                    f"hitter_whiff_bucket={hitter_whiff_bucket}",
                ],
                "by_chase_context": [
                    f"hitter_chase_bucket={hitter_chase_bucket}",
                    f"pitcher_hand={pitcher_hand}",
                    f"hitter_side={hitter_side}",
                ],
            },
        )
        if bip_hit_stage and hit_type_stage:
            bip_hit_distribution = lookup_stage(
                bip_hit_stage,
                {
                    "by_pitch_type": [f"pitch_type={pitch_type}"],
                    "by_matchup": [f"pitcher_hand={pitcher_hand}", f"hitter_side={hitter_side}"],
                    "by_damage_context": [
                        f"pitcher_contact_bucket={pitcher_contact_bucket}",
                        f"hitter_damage_bucket={hitter_damage_bucket}",
                        f"pitch_type={pitch_type}",
                    ],
                    "by_form_and_pitch": [f"pitcher_form_bucket={pitcher_form_bucket}", f"pitch_type={pitch_type}"],
                    "by_matchup_damage": [
                        f"pitcher_hand={pitcher_hand}",
                        f"hitter_side={hitter_side}",
                        f"pitcher_contact_bucket={pitcher_contact_bucket}",
                        f"hitter_damage_bucket={hitter_damage_bucket}",
                    ],
                },
            )
            hit_type_distribution = lookup_stage(
                hit_type_stage,
                {
                    "by_pitch_type": [f"pitch_type={pitch_type}"],
                    "by_matchup": [f"pitcher_hand={pitcher_hand}", f"hitter_side={hitter_side}"],
                    "by_damage_context": [
                        f"pitcher_contact_bucket={pitcher_contact_bucket}",
                        f"hitter_damage_bucket={hitter_damage_bucket}",
                        f"pitch_type={pitch_type}",
                    ],
                    "by_power_context": [
                        f"pitcher_hand={pitcher_hand}",
                        f"hitter_side={hitter_side}",
                        f"pitcher_contact_bucket={pitcher_contact_bucket}",
                        f"hitter_damage_bucket={hitter_damage_bucket}",
                    ],
                    "by_form_and_pitch": [f"pitcher_form_bucket={pitcher_form_bucket}", f"pitch_type={pitch_type}"],
                    "by_air_power": [
                        f"hitter_air_bucket={hitter_air_bucket}",
                        f"hitter_power_bucket={hitter_power_bucket}",
                        f"pitch_type={pitch_type}",
                    ],
                    "by_contact_quality": [
                        f"launch_bucket={launch_bucket}",
                        f"exit_velocity_bucket={exit_velocity_bucket}",
                    ],
                },
            )
        else:
            bip_hit_distribution = {}
            hit_type_distribution = {}

        learned_damage = artifact.get("learned_damage", {})
        if learned_damage:
            damage_feature_map = build_damage_feature_map(
                {
                    "pitch_type": pitch_type,
                    "pitcher_hand": pitcher_hand,
                    "hitter_side": hitter_side,
                    "pitcher_contact_bucket": pitcher_contact_bucket,
                    "hitter_damage_bucket": hitter_damage_bucket,
                    "hitter_air_bucket": hitter_air_bucket,
                    "hitter_power_bucket": hitter_power_bucket,
                    "hitter_recent_hard_hit_rate": 0.35 if exit_velocity_bucket == "soft" else (0.42 if exit_velocity_bucket == "firm" else 0.5),
                    "hitter_recent_air_ball_rate": 0.35 if launch_bucket == "ground" else (0.5 if launch_bucket == "line" else 0.65),
                    "hitter_recent_barrel_proxy_rate": 0.04 if hitter_power_bucket == "limited" else (0.16 if hitter_power_bucket == "impact" else 0.09),
                    "pitcher_hard_hit_rate": 0.28 if pitcher_contact_bucket == "suppresses_damage" else (0.45 if pitcher_contact_bucket == "loud_contact" else 0.35),
                    "pitcher_strikeout_rate": 0.23,
                    "pitcher_walk_rate": 0.08,
                }
            )
            learned_bip_hit_model = learned_damage.get("bip_hit_model")
            learned_hit_type_model = learned_damage.get("hit_type_model")
            if learned_bip_hit_model:
                learned_hit_probability = predict_binary_probability(learned_bip_hit_model, damage_feature_map)
                if bip_hit_distribution:
                    bip_hit_distribution = _normalize_outcome_distribution(
                        {
                            "hit": (bip_hit_distribution.get("hit", 0.0) * 0.45) + (learned_hit_probability * 0.55),
                            "ball_in_play_out": (bip_hit_distribution.get("ball_in_play_out", 0.0) * 0.45) + ((1.0 - learned_hit_probability) * 0.55),
                        }
                    )
            if learned_hit_type_model:
                learned_hit_type_distribution = predict_hit_type_distribution(learned_hit_type_model, damage_feature_map)
                if hit_type_distribution and learned_hit_type_distribution:
                    hit_type_distribution = _normalize_outcome_distribution(
                        {
                            outcome: (hit_type_distribution.get(outcome, 0.0) * 0.4)
                            + (learned_hit_type_distribution.get(outcome, 0.0) * 0.6)
                            for outcome in hit_type_distribution
                        }
                    )

        if pa_stage_distribution and bip_hit_distribution and hit_type_distribution:
            bip = pa_stage_distribution.get("ball_in_play", 0.0)
            bip_hit = bip * bip_hit_distribution.get("hit", 0.0)
            bip_out = bip * bip_hit_distribution.get("ball_in_play_out", 0.0)
            return _normalize_outcome_distribution(
                {
                    "walk": pa_stage_distribution.get("walk", 0.0),
                    "strikeout": pa_stage_distribution.get("strikeout", 0.0),
                    "single": bip_hit * hit_type_distribution.get("single", 0.0),
                    "double": bip_hit * hit_type_distribution.get("double", 0.0),
                    "triple": bip_hit * hit_type_distribution.get("triple", 0.0),
                    "home_run": bip_hit * hit_type_distribution.get("home_run", 0.0),
                    "ball_in_play_out": bip_out,
                }
            )

        damage_stage_distribution = lookup_stage(
            damage_stage,
            {
                "by_pitch_type": [f"pitch_type={pitch_type}"],
                "by_matchup": [f"pitcher_hand={pitcher_hand}", f"hitter_side={hitter_side}"],
                "by_damage_context": [
                    f"pitcher_contact_bucket={pitcher_contact_bucket}",
                    f"hitter_damage_bucket={hitter_damage_bucket}",
                    f"pitch_type={pitch_type}",
                ],
                "by_form_and_pitch": [f"pitcher_form_bucket={pitcher_form_bucket}", f"pitch_type={pitch_type}"],
                "by_matchup_damage": [
                    f"pitcher_hand={pitcher_hand}",
                    f"hitter_side={hitter_side}",
                    f"pitcher_contact_bucket={pitcher_contact_bucket}",
                    f"hitter_damage_bucket={hitter_damage_bucket}",
                ],
            },
        )
        if pa_stage_distribution and damage_stage_distribution:
            bip = pa_stage_distribution.get("ball_in_play", 0.0)
            return _normalize_outcome_distribution(
                {
                    "walk": pa_stage_distribution.get("walk", 0.0),
                    "strikeout": pa_stage_distribution.get("strikeout", 0.0),
                    "single": bip * damage_stage_distribution.get("single", 0.0),
                    "double": bip * damage_stage_distribution.get("double", 0.0),
                    "triple": bip * damage_stage_distribution.get("triple", 0.0),
                    "home_run": bip * damage_stage_distribution.get("home_run", 0.0),
                    "ball_in_play_out": bip * damage_stage_distribution.get("ball_in_play_out", 0.0),
                }
            )

    outcomes = artifact.get("outcomes", [])
    if not outcomes:
        return {}

    segment_specs = {
        "by_pitch_type": [f"pitch_type={pitch_type}"],
        "by_matchup": [f"pitcher_hand={pitcher_hand}", f"hitter_side={hitter_side}"],
        "by_count": [f"count_bucket={count_bucket}"],
        "by_matchup_and_pitch": [
            f"pitcher_hand={pitcher_hand}",
            f"hitter_side={hitter_side}",
            f"pitch_type={pitch_type}",
        ],
        "by_matchup_pitch_count": [
            f"pitcher_hand={pitcher_hand}",
            f"hitter_side={hitter_side}",
            f"pitch_type={pitch_type}",
            f"count_bucket={count_bucket}",
        ],
        "by_form_and_pitch": [
            f"pitcher_form_bucket={pitcher_form_bucket}",
            f"pitch_type={pitch_type}",
        ],
        "by_whiff_buckets": [
            f"pitcher_whiff_bucket={pitcher_whiff_bucket}",
            f"hitter_whiff_bucket={hitter_whiff_bucket}",
            f"pitch_type={pitch_type}",
        ],
        "by_strikeout_context": [
            f"count_bucket={count_bucket}",
            f"pitcher_whiff_bucket={pitcher_whiff_bucket}",
            f"hitter_whiff_bucket={hitter_whiff_bucket}",
        ],
        "by_chase_context": [
            f"hitter_chase_bucket={hitter_chase_bucket}",
            f"pitcher_hand={pitcher_hand}",
            f"hitter_side={hitter_side}",
        ],
    }

    collected: dict[str, list[float]] = {
        outcome: [float(artifact.get("global_outcome_rates", {}).get(outcome, 0.0))] for outcome in outcomes
    }
    for segment_name, parts in segment_specs.items():
        key = "|".join(parts)
        segment = artifact.get("segments", {}).get(segment_name, {}).get("rates", {}).get(key)
        if not segment:
            continue
        for outcome, value in segment.get("outcome_rates", {}).items():
            if outcome in collected:
                collected[outcome].append(float(value))

    averaged = {outcome: sum(values) / len(values) for outcome, values in collected.items()}
    return _normalize_outcome_distribution(averaged)


def _get_hitter_damage_rate(hitter_profile: dict[str, Any] | None, pitch_type: str) -> float | None:
    if not hitter_profile:
        return None
    profile_json = hitter_profile.get("profile_json", {})
    by_pitch = profile_json.get("damage_rate_by_pitch_type", {})
    if isinstance(by_pitch, dict):
        value = by_pitch.get(pitch_type)
        if isinstance(value, (int, float)):
            return float(value)

    by_zone = profile_json.get("damage_rate_by_zone_bucket", {})
    if isinstance(by_zone, dict):
        values = [float(value) for value in by_zone.values() if isinstance(value, (int, float))]
        if values:
            return round(sum(values) / len(values), 4)
    return None


def score_hitter_projection(
    artifacts: BaselineArtifacts | None,
    hitter: dict[str, Any],
    pitcher_hand: str,
    form_profile: dict[str, Any] | None,
    hitter_profile: dict[str, Any] | None,
    manual_pitch_mix_adjustments: dict[str, float],
) -> dict[str, Any]:
    pitch_type = dominant_pitch_type(form_profile, manual_pitch_mix_adjustments)
    hitter_side = hitter.get("batting_side", "R")
    count_bucket = _count_bucket_for_projection(form_profile, manual_pitch_mix_adjustments)
    pitcher_form_bucket = _form_bucket_for_projection(form_profile)
    pitcher_whiff_bucket = _pitcher_whiff_bucket_for_projection(form_profile, pitch_type)
    pitcher_contact_bucket = _pitcher_contact_bucket_for_projection(form_profile)
    hitter_whiff_bucket = _hitter_whiff_bucket_for_projection(hitter_profile, pitch_type)
    hitter_chase_bucket = _hitter_chase_bucket_for_projection(hitter_profile)
    hitter_damage_bucket = _hitter_damage_bucket_for_projection(hitter_profile, pitch_type)
    hitter_air_bucket = _hitter_air_bucket_for_projection(hitter_profile)
    hitter_power_bucket = _hitter_power_bucket_for_projection(hitter_profile)
    launch_bucket, exit_velocity_bucket = _projected_contact_quality_buckets(hitter_profile, form_profile)
    pitcher_metrics = ((form_profile or {}).get("profile_json") or {}).get("overall_metrics", {})
    pitcher_whiff_by_pitch = ((form_profile or {}).get("profile_json") or {}).get("whiff_rate_by_pitch_type", {})

    fallback_swing = float((hitter_profile or {}).get("profile_json", {}).get("swing_rate", 0.47))
    fallback_chase = float((hitter_profile or {}).get("profile_json", {}).get("chase_rate", 0.26) or 0.26)
    fallback_hard_hit = _get_hitter_damage_rate(hitter_profile, pitch_type) or 0.35
    pitcher_whiff = float((pitcher_whiff_by_pitch or {}).get(pitch_type, 0.24) or 0.24)

    if artifacts is None:
        swing_rate = fallback_swing
        whiff_rate = min(0.6, round((pitcher_whiff * 0.65) + 0.08, 4))
        in_play_rate = round(max(0.15, 1.0 - whiff_rate - 0.18), 4)
    else:
        swing_pitch = lookup_segment_rate(
            artifacts.swing,
            "by_pitch_type",
            f"pitch_type={pitch_type}",
            float(artifacts.swing.get("global_positive_rate", fallback_swing)),
        )
        swing_zone = lookup_segment_rate(
            artifacts.swing,
            "by_zone_and_count",
            "zone_bucket=shadow|balls=0|strikes=1",
            float(artifacts.swing.get("global_positive_rate", fallback_swing)),
        )
        swing_matchup = lookup_segment_rate(
            artifacts.swing,
            "by_matchup_and_pitch",
            f"pitcher_hand={pitcher_hand}|hitter_side={hitter_side}|pitch_type={pitch_type}",
            float(artifacts.swing.get("global_positive_rate", fallback_swing)),
        )
        swing_rate = _safe_nested_mean([swing_pitch, swing_zone, swing_matchup, fallback_swing], fallback_swing)

        whiff_pitch = lookup_segment_rate(
            artifacts.contact,
            "by_pitch_type",
            f"pitch_type={pitch_type}",
            float(artifacts.contact.get("whiff_global_rate", pitcher_whiff)),
            artifact_root="whiff_segments",
        )
        whiff_matchup = lookup_segment_rate(
            artifacts.contact,
            "by_matchup",
            f"pitcher_hand={pitcher_hand}|hitter_side={hitter_side}",
            float(artifacts.contact.get("whiff_global_rate", pitcher_whiff)),
            artifact_root="whiff_segments",
        )
        whiff_zone = lookup_segment_rate(
            artifacts.contact,
            "by_zone_pitch",
            f"zone_bucket=shadow|pitch_type={pitch_type}",
            float(artifacts.contact.get("whiff_global_rate", pitcher_whiff)),
            artifact_root="whiff_segments",
        )
        whiff_rate = _safe_nested_mean([whiff_pitch, whiff_matchup, whiff_zone, pitcher_whiff], pitcher_whiff)

        in_play_pitch = lookup_segment_rate(
            artifacts.contact,
            "by_pitch_type",
            f"pitch_type={pitch_type}",
            float(artifacts.contact.get("in_play_global_rate", 0.4)),
            artifact_root="in_play_segments",
        )
        in_play_matchup = lookup_segment_rate(
            artifacts.contact,
            "by_matchup",
            f"pitcher_hand={pitcher_hand}|hitter_side={hitter_side}",
            float(artifacts.contact.get("in_play_global_rate", 0.4)),
            artifact_root="in_play_segments",
        )
        in_play_zone = lookup_segment_rate(
            artifacts.contact,
            "by_zone_pitch",
            f"zone_bucket=shadow|pitch_type={pitch_type}",
            float(artifacts.contact.get("in_play_global_rate", 0.4)),
            artifact_root="in_play_segments",
        )
        in_play_rate = _safe_nested_mean([in_play_pitch, in_play_matchup, in_play_zone], 0.4)

        swing_rate = _clamp(
            swing_rate * _calibration_multiplier(artifacts.swing.get("calibration")),
            0.05,
            0.95,
        )
        whiff_rate = _clamp(
            whiff_rate * _calibration_multiplier(artifacts.contact.get("calibration"), "whiff"),
            0.01,
            0.8,
        )
        in_play_rate = _clamp(
            in_play_rate * _calibration_multiplier(artifacts.contact.get("calibration"), "in_play"),
            0.05,
            0.85,
        )
        whiff_rate, in_play_rate = _normalize_contact_rates(whiff_rate, in_play_rate)

    strikeout_prior = float(pitcher_metrics.get("strikeout_rate", 0.23) or 0.23)
    walk_prior = float(pitcher_metrics.get("walk_rate", 0.08) or 0.08)
    hard_hit_prior = float(pitcher_metrics.get("in_play_hard_hit_rate", fallback_hard_hit) or fallback_hard_hit)

    estimated_k_rate = min(0.5, round((strikeout_prior * 0.55) + (swing_rate * whiff_rate * 0.85), 4))
    estimated_bb_rate = min(0.2, round((walk_prior * 0.7) + ((1.0 - swing_rate) * 0.12) + ((1.0 - fallback_chase) * 0.03), 4))
    hard_hit_rate = min(0.75, round((hard_hit_prior * 0.55) + (fallback_hard_hit * 0.45), 4))
    balls_in_play_rate = max(0.0, round(1.0 - estimated_k_rate - estimated_bb_rate, 4))
    estimated_run_value = round((hard_hit_rate * 0.42) + (estimated_bb_rate * 0.31) - (estimated_k_rate * 0.27), 4)

    hit_on_bip_rate = min(0.5, round(0.19 + (hard_hit_rate * 0.24), 4))
    total_hit_rate = round(balls_in_play_rate * hit_on_bip_rate, 4)
    home_run_share = min(0.22, round(0.04 + (hard_hit_rate * 0.18), 4))
    triple_share = min(0.05, round(0.01 + ((1.0 - hard_hit_rate) * 0.015), 4))
    double_share = min(0.34, round(0.16 + (hard_hit_rate * 0.2), 4))
    single_share = max(0.0, round(1.0 - home_run_share - triple_share - double_share, 4))

    single_rate = round(total_hit_rate * single_share, 4)
    double_rate = round(total_hit_rate * double_share, 4)
    triple_rate = round(total_hit_rate * triple_share, 4)
    home_run_rate = round(total_hit_rate * home_run_share, 4)
    out_in_play_rate = max(
        0.0,
        round(1.0 - estimated_bb_rate - estimated_k_rate - single_rate - double_rate - triple_rate - home_run_rate, 4),
    )

    if artifacts is not None and artifacts.pa_outcomes:
        pa_distribution = _lookup_pa_outcome_distribution(
            artifacts.pa_outcomes,
            pitcher_hand=pitcher_hand,
            hitter_side=hitter_side,
            pitch_type=pitch_type,
            count_bucket=count_bucket,
            pitcher_form_bucket=pitcher_form_bucket,
            pitcher_whiff_bucket=pitcher_whiff_bucket,
            hitter_whiff_bucket=hitter_whiff_bucket,
            hitter_chase_bucket=hitter_chase_bucket,
            pitcher_contact_bucket=pitcher_contact_bucket,
            hitter_damage_bucket=hitter_damage_bucket,
            hitter_air_bucket=hitter_air_bucket,
            hitter_power_bucket=hitter_power_bucket,
            launch_bucket=launch_bucket,
            exit_velocity_bucket=exit_velocity_bucket,
        )
        if pa_distribution:
            calibration = artifacts.pa_outcomes.get("calibration", {})
            calibrated_pa_distribution = {
                outcome: pa_distribution.get(outcome, 0.0) * _calibration_multiplier(calibration, outcome)
                for outcome in pa_distribution
            }
            calibrated_pa_distribution = _normalize_outcome_distribution(calibrated_pa_distribution)

            heuristic_distribution = {
                "walk": estimated_bb_rate,
                "strikeout": estimated_k_rate,
                "single": single_rate,
                "double": double_rate,
                "triple": triple_rate,
                "home_run": home_run_rate,
                "ball_in_play_out": out_in_play_rate,
            }
            heuristic_distribution = _normalize_outcome_distribution(heuristic_distribution)
            blended_distribution = _normalize_outcome_distribution(
                {
                    outcome: (calibrated_pa_distribution.get(outcome, 0.0) * 0.7)
                    + (heuristic_distribution.get(outcome, 0.0) * 0.3)
                    for outcome in heuristic_distribution
                }
            )

            estimated_bb_rate = blended_distribution["walk"]
            estimated_k_rate = blended_distribution["strikeout"]
            single_rate = blended_distribution["single"]
            double_rate = blended_distribution["double"]
            triple_rate = blended_distribution["triple"]
            home_run_rate = blended_distribution["home_run"]
            out_in_play_rate = blended_distribution["ball_in_play_out"]
            balls_in_play_rate = round(
                single_rate + double_rate + triple_rate + home_run_rate + out_in_play_rate,
                4,
            )

    estimated_run_value = round(
        (estimated_bb_rate * 0.33)
        - (estimated_k_rate * 0.27)
        + (single_rate * 0.47)
        + (double_rate * 0.77)
        + (triple_rate * 1.05)
        + (home_run_rate * 1.4)
        + (out_in_play_rate * 0.03),
        4,
    )

    return {
        "hitter_id": hitter["hitter_id"],
        "hitter_name": hitter["hitter_name"],
        "pitch_type_focus": pitch_type,
        "swing_rate": swing_rate,
        "whiff_rate_on_swing": whiff_rate,
        "in_play_rate_on_swing": in_play_rate,
        "hard_hit_rate_on_contact": hard_hit_rate,
        "estimated_k_rate": estimated_k_rate,
        "estimated_bb_rate": estimated_bb_rate,
        "estimated_bip_rate": balls_in_play_rate,
        "single_rate": single_rate,
        "double_rate": double_rate,
        "triple_rate": triple_rate,
        "home_run_rate": home_run_rate,
        "out_in_play_rate": out_in_play_rate,
        "estimated_run_value": estimated_run_value,
    }
