from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_step(args: list[str]) -> None:
    print(f"Running: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def parse_window(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Window arguments must be in the form label=path/to/processed_dir")
    label, raw_path = value.split("=", 1)
    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError("Window labels cannot be empty")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return label, path


def summarize_artifact_metrics(artifact_dir: Path) -> dict[str, Any]:
    swing = read_json(artifact_dir / "swing_model_v1.json")
    contact = read_json(artifact_dir / "contact_model_v1.json")
    pa_outcomes = read_json(artifact_dir / "pa_outcome_model_v1.json")

    pa_summary = {
        outcome: {
            "predicted_rate": metrics["predicted_rate"],
            "observed_rate": metrics["observed_rate"],
            "global_multiplier": metrics["global_multiplier"],
            "brier_score": metrics["brier_score"],
        }
        for outcome, metrics in pa_outcomes.get("calibration", {}).items()
        if outcome in {"walk", "strikeout", "single", "double", "home_run", "ball_in_play_out"}
    }

    return {
        "swing": {
            "training_row_count": swing.get("training_row_count", 0),
            "holdout_row_count": swing.get("holdout_row_count", 0),
            "predicted_rate": swing.get("calibration", {}).get("predicted_rate", 0.0),
            "observed_rate": swing.get("calibration", {}).get("observed_rate", 0.0),
            "global_multiplier": swing.get("calibration", {}).get("global_multiplier", 1.0),
            "brier_score": swing.get("calibration", {}).get("brier_score", 0.0),
        },
        "contact": {
            metric: {
                "training_row_count": contact.get("training_row_count", 0),
                "holdout_row_count": contact.get("holdout_row_count", 0),
                "predicted_rate": contact.get("calibration", {}).get(metric, {}).get("predicted_rate", 0.0),
                "observed_rate": contact.get("calibration", {}).get(metric, {}).get("observed_rate", 0.0),
                "global_multiplier": contact.get("calibration", {}).get(metric, {}).get("global_multiplier", 1.0),
                "brier_score": contact.get("calibration", {}).get(metric, {}).get("brier_score", 0.0),
            }
            for metric in ("whiff", "in_play")
        },
        "pa_outcomes": pa_summary,
    }


def build_markdown_report(window_summaries: list[dict[str, Any]]) -> str:
    lines = ["# Model Window Evaluation", ""]
    lines.append("| Window | Metric | Predicted | Observed | Multiplier | Brier |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")

    for summary in window_summaries:
        label = summary["label"]
        swing = summary["metrics"]["swing"]
        lines.append(
            f"| {label} | swing | {swing['predicted_rate']:.4f} | {swing['observed_rate']:.4f} | {swing['global_multiplier']:.4f} | {swing['brier_score']:.4f} |"
        )
        for metric_name, metrics in summary["metrics"]["contact"].items():
            lines.append(
                f"| {label} | contact_{metric_name} | {metrics['predicted_rate']:.4f} | {metrics['observed_rate']:.4f} | {metrics['global_multiplier']:.4f} | {metrics['brier_score']:.4f} |"
            )
        for outcome_name, metrics in summary["metrics"]["pa_outcomes"].items():
            lines.append(
                f"| {label} | pa_{outcome_name} | {metrics['predicted_rate']:.4f} | {metrics['observed_rate']:.4f} | {metrics['global_multiplier']:.4f} | {metrics['brier_score']:.4f} |"
            )

    lines.extend(["", "## Notes", ""])
    for summary in window_summaries:
        label = summary["label"]
        pa = summary["metrics"]["pa_outcomes"]
        most_miscalibrated = sorted(
            pa.items(),
            key=lambda item: abs(item[1]["global_multiplier"] - 1.0),
            reverse=True,
        )[:2]
        note = ", ".join(
            f"{name} ({metrics['global_multiplier']:.2f}x)"
            for name, metrics in most_miscalibrated
        )
        lines.append(f"- `{label}`: biggest PA calibration drift is in {note}.")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train and compare baseline artifacts across multiple processed windows.")
    parser.add_argument(
        "--window",
        action="append",
        required=True,
        type=parse_window,
        help="Window definition in the form label=path/to/processed_dir. Repeat for multiple windows.",
    )
    parser.add_argument(
        "--artifact-root",
        default="artifacts/models/eval_windows",
        help="Directory where per-window trained artifacts should be written.",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/reports/model_window_evaluation.json",
        help="Path for the combined JSON evaluation report.",
    )
    parser.add_argument(
        "--output-markdown",
        default="artifacts/reports/model_window_evaluation.md",
        help="Path for the combined Markdown evaluation report.",
    )
    parser.add_argument(
        "--holdout-fraction",
        type=float,
        default=0.2,
        help="Fraction of most recent games to reserve inside each window.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    python_executable = sys.executable
    artifact_root = (PROJECT_ROOT / args.artifact_root).resolve()
    output_json = (PROJECT_ROOT / args.output_json).resolve()
    output_markdown = (PROJECT_ROOT / args.output_markdown).resolve()

    window_summaries: list[dict[str, Any]] = []
    for label, input_dir in args.window:
        if not input_dir.exists():
            raise FileNotFoundError(f"Processed window directory not found: {input_dir}")

        window_artifact_dir = artifact_root / label
        run_step(
            [
                python_executable,
                str(PROJECT_ROOT / "services/modeling/train_swing_model.py"),
                "--input-dir",
                str(input_dir),
                "--output",
                str(window_artifact_dir / "swing_model_v1.json"),
                "--holdout-fraction",
                str(args.holdout_fraction),
            ]
        )
        run_step(
            [
                python_executable,
                str(PROJECT_ROOT / "services/modeling/train_contact_model.py"),
                "--input-dir",
                str(input_dir),
                "--output",
                str(window_artifact_dir / "contact_model_v1.json"),
                "--holdout-fraction",
                str(args.holdout_fraction),
            ]
        )
        run_step(
            [
                python_executable,
                str(PROJECT_ROOT / "services/modeling/train_pa_outcome_model.py"),
                "--input-dir",
                str(input_dir),
                "--output",
                str(window_artifact_dir / "pa_outcome_model_v1.json"),
                "--holdout-fraction",
                str(args.holdout_fraction),
            ]
        )

        window_summaries.append(
            {
                "label": label,
                "input_dir": str(input_dir),
                "artifact_dir": str(window_artifact_dir),
                "metrics": summarize_artifact_metrics(window_artifact_dir),
            }
        )

    json_payload = {
        "window_count": len(window_summaries),
        "holdout_fraction": args.holdout_fraction,
        "windows": window_summaries,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    markdown = build_markdown_report(window_summaries)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(markdown, encoding="utf-8")

    print(f"Wrote JSON report to {output_json}")
    print(f"Wrote Markdown report to {output_markdown}")


if __name__ == "__main__":
    main()
