from __future__ import annotations

import json
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MLB_STATS_API_BASE_URL = "https://statsapi.mlb.com/api/v1"


def _request_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{MLB_STATS_API_BASE_URL}{path}{query}",
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
        return json.load(response)


@lru_cache(maxsize=8)
def fetch_mlb_teams(season: int) -> list[dict[str, Any]]:
    payload = _request_json("/teams", {"sportId": 1, "season": season})
    return payload.get("teams", [])


def resolve_team_id(team_key: str, season: int) -> int | None:
    normalized = team_key.strip().lower()
    for team in fetch_mlb_teams(season):
        candidates = {
            str(team.get("id", "")).lower(),
            str(team.get("abbreviation", "")).lower(),
            str(team.get("fileCode", "")).lower(),
            str(team.get("teamCode", "")).lower(),
            str(team.get("clubName", "")).lower(),
            str(team.get("name", "")).lower(),
            str(team.get("teamName", "")).lower(),
        }
        if normalized in candidates:
            team_id = team.get("id")
            if isinstance(team_id, int):
                return team_id
    return None


def fetch_team_roster(team_key: str, season: int, roster_type: str = "active") -> list[dict[str, Any]]:
    team_id = resolve_team_id(team_key, season)
    if team_id is None:
        return []

    payload = _request_json(
        f"/teams/{team_id}/roster",
        {"rosterType": roster_type, "season": season},
    )
    roster = payload.get("roster", [])
    return [
        {
            "team_id": team_key,
            "mlb_team_id": team_id,
            "player_id": person.get("id"),
            "full_name": person.get("fullName"),
            "jersey_number": entry.get("jerseyNumber"),
            "position": (entry.get("position") or {}).get("abbreviation"),
            "status": (entry.get("status") or {}).get("description"),
        }
        for entry in roster
        for person in [entry.get("person") or {}]
    ]


def fetch_team_schedule(team_key: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    team_id = resolve_team_id(team_key, season=int(start_date[:4]))
    if team_id is None:
        return []

    payload = _request_json(
        "/schedule",
        {
            "sportId": 1,
            "teamId": team_id,
            "startDate": start_date,
            "endDate": end_date,
            "hydrate": "probablePitcher,team",
        },
    )

    games: list[dict[str, Any]] = []
    for date_block in payload.get("dates", []):
        for game in date_block.get("games", []):
            teams = game.get("teams", {})
            away = teams.get("away", {})
            home = teams.get("home", {})
            away_team = away.get("team") or {}
            home_team = home.get("team") or {}
            away_probable = away.get("probablePitcher") or {}
            home_probable = home.get("probablePitcher") or {}
            games.append(
                {
                    "game_id": game.get("gamePk"),
                    "game_date": game.get("officialDate"),
                    "game_datetime": game.get("gameDate"),
                    "home_team_id": str(home_team.get("abbreviation", "")).lower(),
                    "home_team_name": home_team.get("name"),
                    "away_team_id": str(away_team.get("abbreviation", "")).lower(),
                    "away_team_name": away_team.get("name"),
                    "home_probable_pitcher_id": home_probable.get("id"),
                    "home_probable_pitcher_name": home_probable.get("fullName"),
                    "away_probable_pitcher_id": away_probable.get("id"),
                    "away_probable_pitcher_name": away_probable.get("fullName"),
                    "status": ((game.get("status") or {}).get("detailedState")),
                }
            )
    return games
