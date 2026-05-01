from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.modeling.baseline_utils import (
    calibration_bins,
    classification_metrics,
    feature_key,
    load_jsonl,
    resolve_holdout_game_ids,
    smoothed_rate,
    split_rows_by_holdout_games,
    write_json,
)


def train_segment_rates(
    rows: list[dict[str, Any]],
    label_field: str,
    segments: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    global_positive = sum(1 for row in rows if row.get(label_field))
    global_rate = global_positive / len(rows) if rows else 0.0

    outputs: dict[str, dict[str, Any]] = {}
    for segment_name, fields in segments.items():
        totals = Counter()
        positives = Counter()
        for row in rows:
            key = feature_key(row, fields)
            totals[key] += 1
            if row.get(label_field):
                positives[key] += 1

        outputs[segment_name] = {
            "fields": fields,
            "rates": {
                key: {
                    "sample_size": totals[key],
                    "positive_rate": smoothed_rate(positives[key], totals[key], global_rate),
                }
                for key in sorted(totals)
            },
        }
    return outputs


def predict_swing_probability(row: dict[str, Any], artifact: dict[str, Any]) -> float:
    global_rate = float(artifact.get("global_positive_rate", 0.47))
    segment_specs = {
        "by_pitch_type": ["pitch_type"],
        "by_zone_and_count": ["zone_bucket", "balls", "strikes"],
        "by_matchup_and_pitch": ["pitcher_hand", "hitter_side", "pitch_type"],
    }

    predictions = [global_rate]
    for segment_name, fields in segment_specs.items():
        key = feature_key(row, fields)
        rate_info = artifact.get("segments", {}).get(segment_name, {}).get("rates", {}).get(key)
        if rate_info:
            predictions.append(float(rate_info["positive_rate"]))
    return round(sum(predictions) / len(predictions), 4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a lightweight baseline swing model artifact.")
    parser.add_argument("--input-dir", default="data/processed", help="Directory containing pitches.jsonl.")
    parser.add_argument(
        "--output",
        default="artifacts/models/swing_model_v1.json",
        help="Path for the trained swing model artifact.",
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
    input_dir = Path(args.input_dir)
    pitch_rows = load_jsonl(input_dir / "pitches.jsonl")
    if not pitch_rows:
        raise ValueError("No pitch rows found for swing model training")

    holdout_game_ids = resolve_holdout_game_ids(input_dir, args.holdout_fraction)
    training_rows, holdout_rows = split_rows_by_holdout_games(pitch_rows, holdout_game_ids)
    if not training_rows:
        training_rows = pitch_rows
        holdout_rows = []

    segments = {
        "by_pitch_type": ["pitch_type"],
        "by_zone_and_count": ["zone_bucket", "balls", "strikes"],
        "by_matchup_and_pitch": ["pitcher_hand", "hitter_side", "pitch_type"],
    }

    label_field = "swing_flag"
    global_rate = round(sum(1 for row in training_rows if row.get(label_field)) / len(training_rows), 4)
    artifact = {
        "model_name": "swing_model_v1",
        "model_type": "frequency_baseline",
        "label_field": label_field,
        "training_row_count": len(training_rows),
        "holdout_row_count": len(holdout_rows),
        "global_positive_rate": global_rate,
        "segments": train_segment_rates(training_rows, label_field, segments),
    }

    if holdout_rows:
        predictions = [predict_swing_probability(row, artifact) for row in holdout_rows]
        labels = [1 if row.get(label_field) else 0 for row in holdout_rows]
        artifact["calibration"] = {
            **classification_metrics(predictions, labels),
            "holdout_game_count": len(holdout_game_ids),
            "bin_report": calibration_bins(predictions, labels),
        }
    else:
        artifact["calibration"] = {
            **classification_metrics([], []),
            "holdout_game_count": 0,
            "bin_report": [],
        }

    write_json(Path(args.output), artifact)
    print(f"Wrote swing model artifact to {args.output}")


if __name__ == "__main__":
    main()
