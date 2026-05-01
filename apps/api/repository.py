from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ModuleNotFoundError:  # pragma: no cover - exercised in dependency-light environments.
    psycopg = None
    Jsonb = None


@contextmanager
def get_connection() -> Iterator[Any | None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url or psycopg is None:
        yield None
        return

    with psycopg.connect(database_url) as connection:
        yield connection


def fetch_latest_pitcher_form(connection: Any, pitcher_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT form_window_id, window_start, window_end, sample_pitch_count, profile_json
            FROM pitcher_form_windows
            WHERE pitcher_id = %s
            ORDER BY window_end DESC
            LIMIT 1
            """,
            (pitcher_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    form_window_id, window_start, window_end, sample_pitch_count, profile_json = row
    return {
        "form_window_id": form_window_id,
        "window_start": window_start,
        "window_end": window_end,
        "sample_pitch_count": sample_pitch_count,
        "profile_json": profile_json,
    }


def fetch_hitter_profiles(connection: Any, hitter_ids: list[str], split_key: str) -> dict[str, dict[str, Any]]:
    if not hitter_ids:
        return {}

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT hitter_id, season, split_key, profile_json
            FROM hitter_tendency_profiles
            WHERE hitter_id = ANY(%s) AND split_key = %s
            ORDER BY season DESC
            """,
            (hitter_ids, split_key),
        )
        rows = cursor.fetchall()

    profiles: dict[str, dict[str, Any]] = {}
    for hitter_id, season, split_key, profile_json in rows:
        profiles.setdefault(
            hitter_id,
            {
                "hitter_id": hitter_id,
                "season": season,
                "split_key": split_key,
                "profile_json": profile_json,
            },
        )
    return profiles


def fetch_pitcher_hand(connection: Any, pitcher_id: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT throws
            FROM players
            WHERE player_id = %s
            LIMIT 1
            """,
            (pitcher_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None
    return row[0]


def insert_matchup_request(
    connection: Any,
    request_id: str,
    pitcher_id: str,
    opponent_team_id: str,
    lineup_json: list[dict[str, Any]],
    form_window_id: str | None,
    status: str,
) -> None:
    if Jsonb is None:
        raise RuntimeError("psycopg is required to insert matchup requests")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO matchup_requests (
                request_id,
                pitcher_id,
                opponent_team_id,
                lineup_json,
                form_window_id,
                status
            )
            VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            """,
            (request_id, pitcher_id, opponent_team_id, Jsonb(lineup_json), form_window_id, status),
        )


def insert_simulation_run(
    connection: Any,
    simulation_id: str,
    request_id: str,
    model_version: str,
    iteration_count: int,
    result_json: dict[str, Any],
) -> None:
    if Jsonb is None:
        raise RuntimeError("psycopg is required to insert simulation runs")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO simulation_runs (
                simulation_id,
                request_id,
                model_version,
                iteration_count,
                result_json
            )
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (simulation_id, request_id, model_version, iteration_count, Jsonb(result_json)),
        )


def _saved_matchup_from_row(row: Any) -> dict[str, Any]:
    (
        request_id,
        pitcher_id,
        opponent_team_id,
        created_at,
        status,
        model_version,
        result_json,
    ) = row
    return {
        "request_id": request_id,
        "pitcher_id": pitcher_id,
        "opponent_team_id": opponent_team_id,
        "created_at": created_at,
        "status": status,
        "model_version": model_version,
        "result_json": result_json,
    }


def fetch_saved_matchup(connection: Any, request_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                mr.request_id,
                mr.pitcher_id,
                mr.opponent_team_id,
                mr.created_at,
                mr.status,
                sr.model_version,
                sr.result_json
            FROM matchup_requests mr
            LEFT JOIN LATERAL (
                SELECT model_version, result_json
                FROM simulation_runs
                WHERE request_id = mr.request_id
                ORDER BY created_at DESC
                LIMIT 1
            ) sr ON TRUE
            WHERE mr.request_id = %s
            """,
            (request_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None
    return _saved_matchup_from_row(row)


def fetch_recent_saved_matchups(connection: Any, limit: int = 20) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                mr.request_id,
                mr.pitcher_id,
                mr.opponent_team_id,
                mr.created_at,
                mr.status,
                sr.model_version,
                sr.result_json
            FROM matchup_requests mr
            LEFT JOIN LATERAL (
                SELECT model_version, result_json
                FROM simulation_runs
                WHERE request_id = mr.request_id
                ORDER BY created_at DESC
                LIMIT 1
            ) sr ON TRUE
            ORDER BY mr.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()

    return [_saved_matchup_from_row(row) for row in rows]


def fetch_teams(connection: Any, season: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    query = """
        SELECT team_id, name, league, season
        FROM teams
        WHERE team_id <> 'unknown'
    """
    params: list[Any] = []
    if season is not None:
        query += " AND season = %s"
        params.append(season)
    query += " ORDER BY season DESC, name ASC LIMIT %s"
    params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    return [
        {
            "team_id": team_id,
            "name": name,
            "league": league,
            "season": season_value,
        }
        for team_id, name, league, season_value in rows
    ]


def fetch_lineup_candidates(connection: Any, team_id: str, limit: int = 15) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                pa.hitter_id,
                COALESCE(p.name, pa.hitter_id) AS hitter_name,
                p.bats,
                COUNT(*) AS plate_appearance_count,
                MAX(g.game_date)::text AS most_recent_game_date
            FROM plate_appearances pa
            LEFT JOIN players p ON p.player_id = pa.hitter_id
            LEFT JOIN games g ON g.game_id = pa.game_id
            WHERE pa.batting_team_id = %s
            GROUP BY pa.hitter_id, p.name, p.bats
            ORDER BY plate_appearance_count DESC, hitter_name ASC
            LIMIT %s
            """,
            (team_id, limit),
        )
        rows = cursor.fetchall()

    return [
        {
            "hitter_id": hitter_id,
            "hitter_name": hitter_name,
            "batting_side": bats,
            "plate_appearance_count": plate_appearance_count,
            "most_recent_game_date": most_recent_game_date,
        }
        for hitter_id, hitter_name, bats, plate_appearance_count, most_recent_game_date in rows
    ]


def fetch_pitcher_candidates(
    connection: Any,
    limit: int = 25,
    search: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT
            x.pitcher_id,
            COALESCE(p.name, x.pitcher_id) AS pitcher_name,
            p.throws,
            COUNT(*) AS pitch_count,
            MAX(g.game_date)::text AS most_recent_game_date
        FROM pitches x
        LEFT JOIN players p ON p.player_id = x.pitcher_id
        LEFT JOIN games g ON g.game_id = x.game_id
        WHERE 1 = 1
    """
    params: list[Any] = []
    if search:
        query += " AND (x.pitcher_id ILIKE %s OR COALESCE(p.name, x.pitcher_id) ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])
    query += """
        GROUP BY x.pitcher_id, p.name, p.throws
        ORDER BY pitch_count DESC, pitcher_name ASC
        LIMIT %s
    """
    params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    return [
        {
            "pitcher_id": pitcher_id,
            "pitcher_name": pitcher_name,
            "throws": throws,
            "pitch_count": pitch_count,
            "most_recent_game_date": most_recent_game_date,
        }
        for pitcher_id, pitcher_name, throws, pitch_count, most_recent_game_date in rows
    ]


def fetch_bullpen_candidates(
    connection: Any,
    team_id: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                pa.pitcher_id,
                COALESCE(p.name, pa.pitcher_id) AS pitcher_name,
                p.throws,
                COUNT(px.pitch_id) AS pitch_count,
                COUNT(DISTINCT pa.game_id) AS game_count,
                MAX(g.game_date)::text AS most_recent_game_date
            FROM plate_appearances pa
            LEFT JOIN players p ON p.player_id = pa.pitcher_id
            LEFT JOIN games g ON g.game_id = pa.game_id
            LEFT JOIN pitches px ON px.pa_id = pa.pa_id
            WHERE pa.fielding_team_id = %s
            GROUP BY pa.pitcher_id, p.name, p.throws
            HAVING COUNT(px.pitch_id) <= 120
            ORDER BY game_count ASC, pitch_count ASC, pitcher_name ASC
            LIMIT %s
            """,
            (team_id, limit),
        )
        rows = cursor.fetchall()

    return [
        {
            "pitcher_id": pitcher_id,
            "pitcher_name": pitcher_name,
            "throws": throws,
            "pitch_count": pitch_count,
            "most_recent_game_date": most_recent_game_date,
        }
        for pitcher_id, pitcher_name, throws, pitch_count, _game_count, most_recent_game_date in rows
    ]


def fetch_team(connection: Any, team_id: str) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT team_id, name, league, season
            FROM teams
            WHERE team_id = %s
            ORDER BY season DESC
            LIMIT 1
            """,
            (team_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None
    team_id_value, name, league, season = row
    return {
        "team_id": team_id_value,
        "name": name,
        "league": league,
        "season": season,
    }


def fetch_pitcher_candidate(connection: Any, pitcher_id: str) -> dict[str, Any] | None:
    candidates = fetch_pitcher_candidates(connection, limit=1, search=pitcher_id)
    for candidate in candidates:
        if candidate["pitcher_id"] == pitcher_id:
            return candidate
    return None


def fetch_player_by_mlbam_id(connection: Any, mlbam_id: int) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT player_id, name, bats, throws, primary_role
            FROM players
            WHERE mlbam_id = %s
            LIMIT 1
            """,
            (mlbam_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    player_id, name, bats, throws, primary_role = row
    return {
        "player_id": player_id,
        "name": name,
        "bats": bats,
        "throws": throws,
        "primary_role": primary_role,
    }
