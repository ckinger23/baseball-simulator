from __future__ import annotations

import argparse
from pathlib import Path

import psycopg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply the project Postgres schema file.")
    parser.add_argument("--database-url", required=True, help="Postgres connection string.")
    parser.add_argument(
        "--schema-path",
        default="infrastructure/sql/001_init.sql",
        help="Path to the SQL schema file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    schema_sql = Path(args.schema_path).read_text(encoding="utf-8")

    with psycopg.connect(args.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema_sql)
        connection.commit()

    print(f"Applied schema from {args.schema_path}")


if __name__ == "__main__":
    main()
