from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MLB_PEOPLE_ENDPOINT = "https://statsapi.mlb.com/api/v1/people"
DEFAULT_BATCH_SIZE = 50


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def batched(values: list[int], size: int) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def fetch_people(person_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not person_ids:
        return {}

    query = urlencode({"personIds": ",".join(str(person_id) for person_id in person_ids)})
    request = Request(
        f"{MLB_PEOPLE_ENDPOINT}?{query}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.mlb.com/",
        },
    )
    with urlopen(request) as response:
        payload = json.load(response)

    return {
        int(person["id"]): person
        for person in payload.get("people", [])
        if person.get("id") is not None
    }


def enrich_player_rows(
    rows: list[dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
    pause_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    ids = sorted({int(row["mlbam_id"]) for row in rows if row.get("mlbam_id") is not None})
    people_by_id: dict[int, dict[str, Any]] = {}

    for batch in batched(ids, batch_size):
        people_by_id.update(fetch_people(batch))
        if pause_seconds > 0:
            time.sleep(pause_seconds)

    enriched_rows = []
    for row in rows:
        mlbam_id = row.get("mlbam_id")
        person = people_by_id.get(int(mlbam_id)) if mlbam_id is not None else None
        if person is None:
            enriched_rows.append(row)
            continue

        full_name = person.get("fullName") or row.get("name")
        bat_side = (person.get("batSide") or {}).get("code") or row.get("bats")
        pitch_hand = (person.get("pitchHand") or {}).get("code") or row.get("throws")

        enriched_rows.append(
            {
                **row,
                "name": full_name,
                "bats": bat_side,
                "throws": pitch_hand if row.get("primary_role") in {"pitcher", "two_way"} else row.get("throws"),
            }
        )

    return enriched_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich player identities using the MLB Stats API people endpoint.")
    parser.add_argument("--input", default="data/processed/players.jsonl", help="Input players JSONL path.")
    parser.add_argument("--output", default=None, help="Output path. Defaults to overwriting the input file.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Number of player IDs per request.")
    parser.add_argument("--pause-seconds", type=float, default=0.0, help="Optional pause between batches.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path
    rows = load_jsonl(input_path)
    enriched = enrich_player_rows(rows, batch_size=args.batch_size, pause_seconds=args.pause_seconds)
    write_jsonl(output_path, enriched)
    print(f"Enriched {len(enriched)} player rows into {output_path}")


if __name__ == "__main__":
    main()
