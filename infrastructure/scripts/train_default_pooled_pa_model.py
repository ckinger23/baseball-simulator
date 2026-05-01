from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.scripts.evaluate_model_windows import parse_window


def run_step(args: list[str]) -> None:
    print(f"Running: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train the default PA outcome artifact from one or more processed windows."
    )
    parser.add_argument(
        "--window",
        action="append",
        required=True,
        type=parse_window,
        help="Training window in the form label=path/to/processed_dir. Repeat to pool multiple windows.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/models/pa_outcome_model_v1.json",
        help="Path for the default pooled PA outcome artifact.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    python_executable = sys.executable
    output = (PROJECT_ROOT / args.output).resolve()

    cmd = [
        python_executable,
        str(PROJECT_ROOT / "services/modeling/train_pa_outcome_model.py"),
        "--output",
        str(output),
        "--holdout-fraction",
        "0",
    ]
    for _, input_dir in args.window:
        cmd.extend(["--input-dir", str(input_dir)])
    run_step(cmd)
    print(f"Wrote default pooled PA artifact to {output}")


if __name__ == "__main__":
    main()
