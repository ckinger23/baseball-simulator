from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.scripts.evaluate_model_windows import parse_window
from services.modeling.baseline_utils import calibration_bins, classification_metrics
from services.modeling.train_pa_outcome_model import OUTCOMES, build_pa_training_rows, predict_outcome_distribution


def run_step(args: list[str]) -> None:
    print(f"Running: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_artifact_on_rows(artifact: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for outcome in OUTCOMES:
        predictions = [predict_outcome_distribution(row, artifact)[outcome] for row in rows]
        labels = [1 if row["outcome"] == outcome else 0 for row in rows]
        metrics[outcome] = {
            **classification_metrics(predictions, labels),
            "bin_report": calibration_bins(predictions, labels),
        }
    return metrics


def build_markdown_report(payload: dict[str, Any]) -> str:
    lines = ["# Pooled PA Outcome Evaluation", ""]
    lines.append("## Training Windows")
    lines.append("")
    for label in payload["train_labels"]:
        lines.append(f"- `{label}`")

    lines.extend(["", "| Eval Window | Outcome | Predicted | Observed | Multiplier | Brier |", "| --- | --- | ---: | ---: | ---: | ---: |"])
    for evaluation in payload["evaluations"]:
        label = evaluation["label"]
        for outcome in ("walk", "strikeout", "single", "double", "home_run", "ball_in_play_out"):
            metrics = evaluation["metrics"][outcome]
            lines.append(
                f"| {label} | {outcome} | {metrics['predicted_rate']:.4f} | {metrics['observed_rate']:.4f} | {metrics['global_multiplier']:.4f} | {metrics['brier_score']:.4f} |"
            )

    lines.extend(["", "## Notes", ""])
    for evaluation in payload["evaluations"]:
        strikeout = evaluation["metrics"]["strikeout"]
        lines.append(
            f"- `{evaluation['label']}`: strikeout multiplier is {strikeout['global_multiplier']:.2f}x on {strikeout['sample_size']} validation PAs."
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train one pooled PA outcome artifact and evaluate it on one or more windows.")
    parser.add_argument(
        "--train-window",
        action="append",
        required=True,
        type=parse_window,
        help="Training window in the form label=path/to/processed_dir. Repeat to pool multiple windows.",
    )
    parser.add_argument(
        "--eval-window",
        action="append",
        required=True,
        type=parse_window,
        help="Evaluation window in the form label=path/to/processed_dir. Repeat for multiple validations.",
    )
    parser.add_argument(
        "--artifact-output",
        default="artifacts/models/pooled/pa_outcome_model_v1.json",
        help="Path for the pooled PA outcome artifact.",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/reports/pooled_pa_evaluation.json",
        help="Path for the pooled evaluation JSON report.",
    )
    parser.add_argument(
        "--output-markdown",
        default="artifacts/reports/pooled_pa_evaluation.md",
        help="Path for the pooled evaluation Markdown report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    python_executable = sys.executable
    artifact_output = (PROJECT_ROOT / args.artifact_output).resolve()
    output_json = (PROJECT_ROOT / args.output_json).resolve()
    output_markdown = (PROJECT_ROOT / args.output_markdown).resolve()

    train_windows = args.train_window
    eval_windows = args.eval_window

    train_cmd = [
        python_executable,
        str(PROJECT_ROOT / "services/modeling/train_pa_outcome_model.py"),
        "--output",
        str(artifact_output),
        "--holdout-fraction",
        "0",
    ]
    for _, input_dir in train_windows:
        train_cmd.extend(["--input-dir", str(input_dir)])
    run_step(train_cmd)

    artifact = read_json(artifact_output)
    evaluations: list[dict[str, Any]] = []
    for label, input_dir in eval_windows:
        rows = build_pa_training_rows(input_dir)
        evaluations.append(
            {
                "label": label,
                "input_dir": str(input_dir),
                "row_count": len(rows),
                "metrics": evaluate_artifact_on_rows(artifact, rows),
            }
        )

    payload = {
        "train_labels": [label for label, _ in train_windows],
        "train_input_dirs": [str(path) for _, path in train_windows],
        "artifact_path": str(artifact_output),
        "evaluations": evaluations,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(build_markdown_report(payload), encoding="utf-8")
    print(f"Wrote JSON report to {output_json}")
    print(f"Wrote Markdown report to {output_markdown}")


if __name__ == "__main__":
    main()
