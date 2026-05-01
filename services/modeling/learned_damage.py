from __future__ import annotations

import math
from typing import Any


FEATURE_NAMES = (
    "hitter_recent_hard_hit_rate",
    "hitter_recent_air_ball_rate",
    "hitter_recent_barrel_proxy_rate",
    "pitcher_hard_hit_rate",
    "pitcher_strikeout_rate",
    "pitcher_walk_rate",
    "same_side_matchup",
    "lefty_hitter",
    "lefty_pitcher",
    "pitch_family_fastball",
    "pitch_family_breaking",
    "pitch_family_offspeed",
    "hitter_air_lifted",
    "hitter_air_ground_heavy",
    "hitter_power_impact",
    "hitter_power_limited",
    "pitcher_contact_loud",
    "pitcher_contact_suppresses",
)


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp_value = math.exp(-value)
        return 1.0 / (1.0 + exp_value)
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def pitch_family(pitch_type: str) -> str:
    normalized = (pitch_type or "").lower()
    if any(token in normalized for token in ("fastball", "sinker", "cutter")):
        return "fastball"
    if any(token in normalized for token in ("slider", "curve", "sweeper", "slurve")):
        return "breaking"
    return "offspeed"


def build_damage_feature_map(row: dict[str, Any]) -> dict[str, float]:
    pitch_type = str(row.get("pitch_type") or "")
    family = pitch_family(pitch_type)
    pitcher_hand = str(row.get("pitcher_hand") or "")
    hitter_side = str(row.get("hitter_side") or "")
    hitter_air_bucket = str(row.get("hitter_air_bucket") or "")
    hitter_power_bucket = str(row.get("hitter_power_bucket") or "")
    pitcher_contact_bucket = str(row.get("pitcher_contact_bucket") or "")

    return {
        "hitter_recent_hard_hit_rate": float(row.get("hitter_recent_hard_hit_rate") or 0.35),
        "hitter_recent_air_ball_rate": float(row.get("hitter_recent_air_ball_rate") or 0.45),
        "hitter_recent_barrel_proxy_rate": float(row.get("hitter_recent_barrel_proxy_rate") or 0.08),
        "pitcher_hard_hit_rate": float(row.get("pitcher_hard_hit_rate") or 0.35),
        "pitcher_strikeout_rate": float(row.get("pitcher_strikeout_rate") or 0.23),
        "pitcher_walk_rate": float(row.get("pitcher_walk_rate") or 0.08),
        "same_side_matchup": 1.0 if pitcher_hand and hitter_side and pitcher_hand == hitter_side else 0.0,
        "lefty_hitter": 1.0 if hitter_side == "L" else 0.0,
        "lefty_pitcher": 1.0 if pitcher_hand == "L" else 0.0,
        "pitch_family_fastball": 1.0 if family == "fastball" else 0.0,
        "pitch_family_breaking": 1.0 if family == "breaking" else 0.0,
        "pitch_family_offspeed": 1.0 if family == "offspeed" else 0.0,
        "hitter_air_lifted": 1.0 if hitter_air_bucket == "lifted" else 0.0,
        "hitter_air_ground_heavy": 1.0 if hitter_air_bucket == "ground_heavy" else 0.0,
        "hitter_power_impact": 1.0 if hitter_power_bucket == "impact" else 0.0,
        "hitter_power_limited": 1.0 if hitter_power_bucket == "limited" else 0.0,
        "pitcher_contact_loud": 1.0 if pitcher_contact_bucket == "loud_contact" else 0.0,
        "pitcher_contact_suppresses": 1.0 if pitcher_contact_bucket == "suppresses_damage" else 0.0,
    }


def _fit_standardization(feature_rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for name in FEATURE_NAMES:
        values = [float(row.get(name, 0.0)) for row in feature_rows]
        mean = sum(values) / len(values) if values else 0.0
        variance = sum((value - mean) ** 2 for value in values) / len(values) if values else 0.0
        std = math.sqrt(variance) or 1.0
        stats[name] = {"mean": mean, "std": std}
    return stats


def _vectorize(feature_map: dict[str, float], stats: dict[str, dict[str, float]]) -> list[float]:
    vector: list[float] = []
    for name in FEATURE_NAMES:
        mean = stats[name]["mean"]
        std = stats[name]["std"]
        vector.append((float(feature_map.get(name, 0.0)) - mean) / std)
    return vector


def fit_binary_logistic(
    feature_rows: list[dict[str, float]],
    labels: list[int],
    epochs: int = 250,
    learning_rate: float = 0.08,
    l2: float = 0.001,
) -> dict[str, Any]:
    stats = _fit_standardization(feature_rows)
    matrix = [_vectorize(row, stats) for row in feature_rows]
    weights = [0.0 for _ in FEATURE_NAMES]
    bias = 0.0
    sample_count = len(matrix) or 1

    for _ in range(epochs):
        gradient_w = [0.0 for _ in FEATURE_NAMES]
        gradient_b = 0.0
        for vector, label in zip(matrix, labels):
            score = bias + sum(weight * value for weight, value in zip(weights, vector))
            prediction = _sigmoid(score)
            error = prediction - label
            for index, value in enumerate(vector):
                gradient_w[index] += error * value
            gradient_b += error

        for index in range(len(weights)):
            gradient = (gradient_w[index] / sample_count) + (l2 * weights[index])
            weights[index] -= learning_rate * gradient
        bias -= learning_rate * (gradient_b / sample_count)

    return {
        "feature_names": list(FEATURE_NAMES),
        "feature_stats": stats,
        "weights": weights,
        "bias": bias,
    }


def predict_binary_probability(model: dict[str, Any], feature_map: dict[str, float]) -> float:
    stats = model.get("feature_stats", {})
    if not stats:
        return 0.5
    vector = _vectorize(feature_map, stats)
    weights = [float(value) for value in model.get("weights", [])]
    bias = float(model.get("bias", 0.0))
    score = bias + sum(weight * value for weight, value in zip(weights, vector))
    return round(_sigmoid(score), 4)


def fit_hit_type_models(feature_rows: list[dict[str, float]], labels: list[str]) -> dict[str, Any]:
    classes = ("single", "double", "triple", "home_run")
    return {
        "classes": list(classes),
        "models": {
            klass: fit_binary_logistic(feature_rows, [1 if label == klass else 0 for label in labels], epochs=220, learning_rate=0.07)
            for klass in classes
        },
    }


def predict_hit_type_distribution(model: dict[str, Any], feature_map: dict[str, float]) -> dict[str, float]:
    classes = model.get("classes", [])
    if not classes:
        return {}
    raw_scores = {
        klass: predict_binary_probability(model["models"][klass], feature_map)
        for klass in classes
    }
    total = sum(raw_scores.values()) or 1.0
    return {klass: round(value / total, 4) for klass, value in raw_scores.items()}
