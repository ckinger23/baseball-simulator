from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_step(args: list[str]) -> None:
    print(f"Running: {' '.join(args)}")
    subprocess.run(args, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the initial local pipeline end to end.")
    parser.add_argument("--start-date", required=True, help="Inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date in YYYY-MM-DD format.")
    parser.add_argument(
        "--raw-csv",
        default=None,
        help="Optional local Statcast CSV path. When set, skip download and use this file instead.",
    )
    parser.add_argument(
        "--raw-output",
        default=None,
        help="Optional raw CSV output path. Defaults to data/raw/statcast_<start>_<end>.csv.",
    )
    parser.add_argument("--processed-dir", default="data/processed", help="Directory for processed JSONL outputs.")
    parser.add_argument("--window-days", type=int, default=30, help="Pitcher form window length.")
    parser.add_argument("--database-url", default=None, help="Optional Postgres connection string.")
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Apply the project schema before loading processed artifacts into Postgres.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[2]
    python_executable = sys.executable
    raw_output = args.raw_output or f"data/raw/statcast_{args.start_date}_{args.end_date}.csv"

    statcast_cmd = [
        python_executable,
        str(project_root / "services/etl/statcast_pull.py"),
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
        "--output",
        raw_output,
    ]
    if args.raw_csv:
        statcast_cmd.extend(["--source-csv", args.raw_csv])
    run_step(statcast_cmd)

    run_step(
        [
            python_executable,
            str(project_root / "services/etl/build_features.py"),
            "--input",
            raw_output,
            "--output-dir",
            args.processed_dir,
        ]
    )

    run_step(
        [
            python_executable,
            str(project_root / "services/etl/enrich_players.py"),
            "--input",
            str(Path(args.processed_dir) / "players.jsonl"),
        ]
    )

    run_step(
        [
            python_executable,
            str(project_root / "services/etl/build_profiles.py"),
            "--input-dir",
            args.processed_dir,
            "--output-dir",
            args.processed_dir,
            "--window-days",
            str(args.window_days),
        ]
    )

    if args.database_url:
        if args.apply_schema:
            run_step(
                [
                    python_executable,
                    str(project_root / "infrastructure/scripts/apply_schema.py"),
                    "--database-url",
                    args.database_url,
                ]
            )

        run_step(
            [
                python_executable,
                str(project_root / "services/etl/load_to_postgres.py"),
                "--database-url",
                args.database_url,
                "--input-dir",
                args.processed_dir,
            ]
        )

    print("Bootstrap pipeline complete")


if __name__ == "__main__":
    main()
