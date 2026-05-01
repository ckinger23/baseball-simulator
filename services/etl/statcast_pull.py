from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASEBALL_SAVANT_CSV_URL = "https://baseballsavant.mlb.com/statcast_search/csv"


def build_statcast_url(start_date: str, end_date: str) -> str:
    query = {
        "all": "true",
        "type": "details",
        "game_date_gt": start_date,
        "game_date_lt": end_date,
    }
    return f"{BASEBALL_SAVANT_CSV_URL}?{urlencode(query)}"


def download_csv(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
            ),
            "Referer": "https://baseballsavant.mlb.com/",
            "Accept": "text/csv,application/csv,text/plain,*/*",
        },
    )
    with urlopen(request) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def copy_local_csv(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def count_rows(csv_path: Path) -> int:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for _ in reader)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull or copy a narrow Statcast CSV extract.")
    parser.add_argument("--start-date", required=True, help="Inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date in YYYY-MM-DD format.")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to data/raw/statcast_<start>_<end>.csv.",
    )
    parser.add_argument(
        "--source-csv",
        default=None,
        help="Optional local Statcast CSV path. When provided, the script copies this file instead of downloading.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output or f"data/raw/statcast_{args.start_date}_{args.end_date}.csv")

    if args.source_csv:
        copy_local_csv(Path(args.source_csv), output_path)
        source_label = f"local file {args.source_csv}"
    else:
        url = build_statcast_url(args.start_date, args.end_date)
        download_csv(url, output_path)
        source_label = url

    row_count = count_rows(output_path)
    print(f"Saved {row_count} rows to {output_path} from {source_label}")


if __name__ == "__main__":
    main()
