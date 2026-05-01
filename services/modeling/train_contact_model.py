from __future__ import annotations

import argparse
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

def train_binary_rates(
    rows: list[dict[str, Any]],
    label_field: str,
    segments: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    global_positive = sum(1 for row in rows if row.get(label_field))
    global_rate = global_positive / len(rows) if rows else 0.0
    outputs: dict[str, dict[str, Any]] = {}

    for segment_name, fields in segments.items():
        totals: dict[str, int] = {}
        positives: dict[str, int] = {}
        for row in rows:
            key = feature_key(row, fields)
            totals[key] = totals.get(key, 0) + 1
            if row.get(label_field):
                positives[key] = positives.get(key, 0) + 1

        outputs[segment_name] = {
            "fields": fields,
            "rates": {
                key: {
                    "sample_size": totals[key],
                    "positive_rate": smoothed_rate(positives.get(key, 0), totals[key], global_rate, prior_weight=20),
                }
                for key in sorted(totals)
            },
        }
    return outputs


def predict_contact_probability(
    row: dict[str, Any],
    artifact: dict[str, Any],
    target: str,
) -> float:
    if target == "whiff":
        global_rate = float(artifact.get("whiff_global_rate", 0.24))
        segment_root = "whiff_segments"
    else:
        global_rate = float(artifact.get("in_play_global_rate", 0.4))
        segment_root = "in_play_segments"

    segment_specs = {
        "by_pitch_type": ["pitch_type"],
        "by_matchup": ["pitcher_hand", "hitter_side"],
        "by_zone_pitch": ["zone_bucket", "pitch_type"],
    }

    predictions = [global_rate]
    for segment_name, fields in segment_specs.items():
        key = feature_key(row, fields)
        rate_info = artifact.get(segment_root, {}).get(segment_name, {}).get("rates", {}).get(key)
        if rate_info:
            predictions.append(float(rate_info["positive_rate"]))
    return round(sum(predictions) / len(predictions), 4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train lightweight baseline contact artifacts.")
    parser.add_argument("--input-dir", default="data/processed", help="Directory containing pitches.jsonl.")
    parser.add_argument(
        "--output",
        default="artifacts/models/contact_model_v1.json",
        help="Path for the trained contact model artifact.",
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
    holdout_game_ids = resolve_holdout_game_ids(input_dir, args.holdout_fraction)
    training_pitch_rows, holdout_pitch_rows = split_rows_by_holdout_games(pitch_rows, holdout_game_ids)

    swing_rows = [row for row in training_pitch_rows if row.get("swing_flag")]
    if not swing_rows:
        raise ValueError("No swing rows found for contact model training")
    holdout_swing_rows = [row for row in holdout_pitch_rows if row.get("swing_flag")]

    whiff_global_rate = round(sum(1 for row in swing_rows if row.get("whiff_flag")) / len(swing_rows), 4)
    in_play_global_rate = round(sum(1 for row in swing_rows if row.get("in_play_flag")) / len(swing_rows), 4)
    segments = {
        "by_pitch_type": ["pitch_type"],
        "by_matchup": ["pitcher_hand", "hitter_side"],
        "by_zone_pitch": ["zone_bucket", "pitch_type"],
    }

    artifact = {
        "model_name": "contact_model_v1",
        "model_type": "frequency_baseline",
        "training_row_count": len(swing_rows),
        "holdout_row_count": len(holdout_swing_rows),
        "whiff_global_rate": whiff_global_rate,
        "in_play_global_rate": in_play_global_rate,
        "whiff_segments": train_binary_rates(swing_rows, "whiff_flag", segments),
        "in_play_segments": train_binary_rates(swing_rows, "in_play_flag", segments),
    }

    if holdout_swing_rows:
        whiff_predictions = [predict_contact_probability(row, artifact, "whiff") for row in holdout_swing_rows]
        whiff_labels = [1 if row.get("whiff_flag") else 0 for row in holdout_swing_rows]
        in_play_predictions = [predict_contact_probability(row, artifact, "in_play") for row in holdout_swing_rows]
        in_play_labels = [1 if row.get("in_play_flag") else 0 for row in holdout_swing_rows]
        artifact["calibration"] = {
            "whiff": {
                **classification_metrics(whiff_predictions, whiff_labels),
                "holdout_game_count": len(holdout_game_ids),
                "bin_report": calibration_bins(whiff_predictions, whiff_labels),
            },
            "in_play": {
                **classification_metrics(in_play_predictions, in_play_labels),
                "holdout_game_count": len(holdout_game_ids),
                "bin_report": calibration_bins(in_play_predictions, in_play_labels),
            },
        }
    else:
        artifact["calibration"] = {
            "whiff": {
                **classification_metrics([], []),
                "holdout_game_count": 0,
                "bin_report": [],
            },
            "in_play": {
                **classification_metrics([], []),
                "holdout_game_count": 0,
                "bin_report": [],
            },
        }

    write_json(Path(args.output), artifact)
    print(f"Wrote contact model artifact to {args.output}")


if __name__ == "__main__":
    main()
