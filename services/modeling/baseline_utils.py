from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def bucket_count(count: int | None) -> str:
    if count is None:
        return "unknown"
    return str(count)


def feature_key(row: dict[str, Any], fields: list[str]) -> str:
    values = []
    for field in fields:
        value = row.get(field)
        if field in {"balls", "strikes"}:
            value = bucket_count(value)
        values.append(f"{field}={value}")
    return "|".join(values)


def smoothed_rate(positive: int, total: int, prior_rate: float, prior_weight: int = 25) -> float:
    return round((positive + (prior_rate * prior_weight)) / (total + prior_weight), 4)


def resolve_holdout_game_ids(input_dir: Path, holdout_fraction: float) -> set[str]:
    if holdout_fraction <= 0:
        return set()
    game_rows = load_jsonl(input_dir / "games.jsonl")
    if not game_rows:
        return set()

    ordered_games = sorted(
        (
            {
                "game_id": str(row["game_id"]),
                "game_date": str(row.get("game_date") or ""),
            }
            for row in game_rows
            if row.get("game_id")
        ),
        key=lambda row: (row["game_date"], row["game_id"]),
    )
    holdout_count = max(1, round(len(ordered_games) * holdout_fraction))
    return {row["game_id"] for row in ordered_games[-holdout_count:]}


def split_rows_by_holdout_games(
    rows: list[dict[str, Any]],
    holdout_game_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not holdout_game_ids:
        return rows, []

    training_rows = [row for row in rows if str(row.get("game_id")) not in holdout_game_ids]
    holdout_rows = [row for row in rows if str(row.get("game_id")) in holdout_game_ids]
    return training_rows, holdout_rows


def calibration_bins(
    predictions: list[float],
    labels: list[int],
    bucket_count: int = 10,
) -> list[dict[str, float | int]]:
    if not predictions or not labels or len(predictions) != len(labels):
        return []

    ranked = sorted(zip(predictions, labels), key=lambda item: item[0])
    chunk_size = max(1, len(ranked) // bucket_count)
    outputs: list[dict[str, float | int]] = []

    for start in range(0, len(ranked), chunk_size):
        chunk = ranked[start : start + chunk_size]
        if not chunk:
            continue
        chunk_predictions = [item[0] for item in chunk]
        chunk_labels = [item[1] for item in chunk]
        outputs.append(
            {
                "sample_size": len(chunk),
                "predicted_rate": round(sum(chunk_predictions) / len(chunk_predictions), 4),
                "observed_rate": round(sum(chunk_labels) / len(chunk_labels), 4),
            }
        )
    return outputs[:bucket_count]


def classification_metrics(predictions: list[float], labels: list[int]) -> dict[str, float]:
    if not predictions or not labels or len(predictions) != len(labels):
        return {
            "sample_size": 0,
            "predicted_rate": 0.0,
            "observed_rate": 0.0,
            "brier_score": 0.0,
            "mean_absolute_error": 0.0,
            "global_multiplier": 1.0,
        }

    sample_size = len(predictions)
    predicted_rate = sum(predictions) / sample_size
    observed_rate = sum(labels) / sample_size
    brier_score = sum((prediction - label) ** 2 for prediction, label in zip(predictions, labels)) / sample_size
    mean_absolute_error = sum(abs(prediction - label) for prediction, label in zip(predictions, labels)) / sample_size
    multiplier = observed_rate / predicted_rate if predicted_rate > 0 else 1.0

    return {
        "sample_size": sample_size,
        "predicted_rate": round(predicted_rate, 4),
        "observed_rate": round(observed_rate, 4),
        "brier_score": round(brier_score, 4),
        "mean_absolute_error": round(mean_absolute_error, 4),
        "global_multiplier": round(multiplier, 4),
    }


def count_by_game(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("game_id")) for row in rows if row.get("game_id"))
