from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api import main
from services.modeling.inference import BaselineArtifacts


@contextmanager
def no_database_connection():
    yield None


def fake_artifacts() -> BaselineArtifacts:
    return BaselineArtifacts(
        swing={
            "global_positive_rate": 0.47,
            "segments": {
                "by_pitch_type": {
                    "rates": {
                        "pitch_type=sl": {"positive_rate": 0.49},
                    }
                },
                "by_zone_and_count": {
                    "rates": {
                        "zone_bucket=shadow|balls=0|strikes=1": {"positive_rate": 0.46},
                    }
                },
                "by_matchup_and_pitch": {
                    "rates": {
                        "pitcher_hand=R|hitter_side=L|pitch_type=sl": {"positive_rate": 0.5},
                        "pitcher_hand=R|hitter_side=R|pitch_type=sl": {"positive_rate": 0.44},
                    }
                },
            },
        },
        contact={
            "whiff_global_rate": 0.24,
            "in_play_global_rate": 0.41,
            "whiff_segments": {
                "by_pitch_type": {"rates": {"pitch_type=sl": {"positive_rate": 0.27}}},
                "by_matchup": {
                    "rates": {
                        "pitcher_hand=R|hitter_side=L": {"positive_rate": 0.25},
                        "pitcher_hand=R|hitter_side=R": {"positive_rate": 0.23},
                    }
                },
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=sl": {"positive_rate": 0.28}}},
            },
            "in_play_segments": {
                "by_pitch_type": {"rates": {"pitch_type=sl": {"positive_rate": 0.39}}},
                "by_matchup": {
                    "rates": {
                        "pitcher_hand=R|hitter_side=L": {"positive_rate": 0.42},
                        "pitcher_hand=R|hitter_side=R": {"positive_rate": 0.4},
                    }
                },
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=sl": {"positive_rate": 0.41}}},
            },
        },
    )


def saved_matchup_payload(request_id: str) -> dict[str, object]:
    return {
        "request_id": request_id,
        "pitcher_id": "pitcher_1001",
        "opponent_team_id": "chc",
        "created_at": datetime.now(UTC),
        "status": "simulated",
        "model_version": "baseline_v1",
        "result_json": {
            "overview": {
                "expected_k_rate": 0.24,
                "expected_bb_rate": 0.08,
                "expected_bip_rate": 0.68,
                "expected_hard_hit_rate": 0.34,
                "estimated_run_value": 0.13,
                "summary": "Saved matchup summary",
            },
            "hitter_projections": [
                {
                    "hitter_id": "hitter_2002",
                    "hitter_name": "Hitter One",
                    "pitch_type_focus": "sl",
                    "swing_rate": 0.48,
                    "whiff_rate_on_swing": 0.26,
                    "in_play_rate_on_swing": 0.39,
                    "hard_hit_rate_on_contact": 0.36,
                    "estimated_k_rate": 0.18,
                    "estimated_bb_rate": 0.08,
                    "estimated_bip_rate": 0.74,
                    "single_rate": 0.15,
                    "double_rate": 0.05,
                    "triple_rate": 0.01,
                    "home_run_rate": 0.03,
                    "out_in_play_rate": 0.48,
                    "estimated_run_value": 0.14,
                }
            ],
            "simulation": {
                "iteration_count": 500,
                "runs_scored": {"mean": 4.1, "p10": 1.0, "p50": 4.0, "p90": 8.0},
                "hits": {"mean": 8.4, "p10": 5.0, "p50": 8.0, "p90": 12.0},
                "home_runs": {"mean": 1.1, "p10": 0.0, "p50": 1.0, "p90": 2.0},
                "plate_appearances": {"mean": 39.8, "p10": 33.0, "p50": 40.0, "p90": 46.0},
                "strikeouts": {"mean": 8.1, "p10": 5.0, "p50": 8.0, "p90": 11.0},
                "walks": {"mean": 3.2, "p10": 1.0, "p50": 3.0, "p90": 6.0},
                "balls_in_play": {"mean": 25.0, "p10": 20.0, "p50": 25.0, "p90": 30.0},
                "hard_hit_balls": {"mean": 5.0, "p10": 2.0, "p50": 5.0, "p90": 8.0},
                "reliever_inherited_runners": {"mean": 0.4, "p10": 0.0, "p50": 0.0, "p90": 2.0},
                "reliever_inherited_runners_scored": {"mean": 0.1, "p10": 0.0, "p50": 0.0, "p90": 1.0},
                "run_value": {"mean": 0.88, "p10": -0.2, "p50": 0.8, "p90": 1.9},
            },
            "next_step": "Persisted matchup retrieved from Postgres.",
        },
    }


def test_matchups_endpoint_returns_richer_response(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_connection", no_database_connection)
    monkeypatch.setattr(main, "load_baseline_artifacts", fake_artifacts)

    client = TestClient(main.app)
    payload = {
        "pitcher_id": "pitcher_1001",
        "pitcher_name": "Pitcher One",
        "opponent_team_id": "chc",
        "lineup": [
            {"hitter_id": "hitter_2002", "hitter_name": "Hitter One", "batting_side": "L", "lineup_spot": 1},
            {"hitter_id": "hitter_2003", "hitter_name": "Hitter Two", "batting_side": "R", "lineup_spot": 2},
        ],
        "manual_pitch_mix_adjustments": {"sl": 0.55, "ff": 0.45},
    }

    response = client.post("/matchups", json=payload)
    assert response.status_code == 201

    body = response.json()
    assert body["status"] == "simulated_without_persistence"
    assert len(body["hitter_projections"]) == 2
    assert body["simulation"]["iteration_count"] == 500
    assert "runs_scored" in body["simulation"]
    assert "plate_appearances" in body["simulation"]
    assert body["hitter_projections"][0]["pitch_type_focus"] == "sl"
    assert body["hitter_projections"][0]["single_rate"] >= 0.0
    assert body["hitter_projections"][0]["out_in_play_rate"] >= 0.0


def test_saved_matchup_endpoints(monkeypatch) -> None:
    first_id = str(uuid4())
    second_id = str(uuid4())
    first_payload = saved_matchup_payload(first_id)
    second_payload = saved_matchup_payload(second_id)
    second_payload["result_json"]["overview"]["expected_k_rate"] = 0.29
    second_payload["result_json"]["simulation"]["runs_scored"]["mean"] = 5.2
    second_payload["result_json"]["simulation"]["home_runs"]["mean"] = 1.6
    second_payload["result_json"]["simulation"]["run_value"]["mean"] = 1.11

    @contextmanager
    def fake_database_connection():
        yield object()

    def fake_fetch_recent_saved_matchups(_connection, limit: int = 20):
        assert limit == 20
        return [second_payload, first_payload]

    def fake_fetch_saved_matchup(_connection, request_id: str):
        if request_id == first_id:
            return first_payload
        if request_id == second_id:
            return second_payload
        return None

    monkeypatch.setattr(main, "get_connection", fake_database_connection)
    monkeypatch.setattr(main, "fetch_recent_saved_matchups", fake_fetch_recent_saved_matchups)
    monkeypatch.setattr(main, "fetch_saved_matchup", fake_fetch_saved_matchup)

    client = TestClient(main.app)

    list_response = client.get("/matchups")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 2

    detail_response = client.get(f"/matchups/{first_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["simulation"]["runs_scored"]["mean"] == 4.1

    compare_response = client.post(
        "/matchups/compare",
        json={"request_ids": [first_id, second_id]},
    )
    assert compare_response.status_code == 200
    comparison_body = compare_response.json()
    assert len(comparison_body["matchups"]) == 2
    assert comparison_body["deltas"][0]["expected_k_rate_delta"] == 0.05
    assert comparison_body["deltas"][0]["runs_scored_mean_delta"] == 1.1


def test_team_and_lineup_candidate_endpoints(monkeypatch) -> None:
    @contextmanager
    def fake_database_connection():
        yield object()

    def fake_fetch_teams(_connection, season=None, limit: int = 50):
        assert season == 2025
        assert limit == 10
        return [
            {"team_id": "sea", "name": "SEA", "league": "MLB", "season": 2025},
            {"team_id": "stl", "name": "STL", "league": "MLB", "season": 2025},
        ]

    def fake_fetch_lineup_candidates(_connection, team_id: str, limit: int = 15):
        assert team_id == "sea"
        assert limit == 9
        return [
            {
                "hitter_id": "hitter_1",
                "hitter_name": "France, Ty",
                "batting_side": "R",
                "plate_appearance_count": 12,
                "most_recent_game_date": "2025-06-04",
            }
        ]

    def fake_fetch_bullpen_candidates(_connection, team_id: str, limit: int = 10):
        assert team_id == "sea"
        assert limit == 5
        return [
            {
                "pitcher_id": "pitcher_relief_1",
                "pitcher_name": "Relief One",
                "throws": "R",
                "pitch_count": 32,
                "most_recent_game_date": "2025-06-04",
            }
        ]

    monkeypatch.setattr(main, "get_connection", fake_database_connection)
    monkeypatch.setattr(main, "fetch_teams", fake_fetch_teams)
    monkeypatch.setattr(main, "fetch_lineup_candidates", fake_fetch_lineup_candidates)
    monkeypatch.setattr(main, "fetch_bullpen_candidates", fake_fetch_bullpen_candidates)

    client = TestClient(main.app)
    teams_response = client.get("/teams?season=2025&limit=10")
    assert teams_response.status_code == 200
    assert teams_response.json()[0]["team_id"] == "sea"

    lineup_response = client.get("/teams/sea/lineup-candidates?limit=9")
    assert lineup_response.status_code == 200
    assert lineup_response.json()[0]["hitter_name"] == "France, Ty"

    bullpen_response = client.get("/teams/sea/bullpen-candidates?limit=5")
    assert bullpen_response.status_code == 200
    assert bullpen_response.json()[0]["pitcher_name"] == "Relief One"


def test_pitcher_and_matchup_draft_endpoints(monkeypatch) -> None:
    @contextmanager
    def fake_database_connection():
        yield object()

    def fake_fetch_pitcher_candidates(_connection, limit: int = 25, search=None):
        assert limit == 10
        assert search == "pitcher_123"
        return [
            {
                "pitcher_id": "pitcher_123",
                "pitcher_name": "Pitcher Example",
                "throws": "R",
                "pitch_count": 88,
                "most_recent_game_date": "2025-06-04",
            }
        ]

    def fake_fetch_pitcher_candidate(_connection, pitcher_id: str):
        assert pitcher_id == "pitcher_123"
        return {
            "pitcher_id": "pitcher_123",
            "pitcher_name": "Pitcher Example",
            "throws": "R",
            "pitch_count": 88,
            "most_recent_game_date": "2025-06-04",
        }

    def fake_fetch_team(_connection, team_id: str):
        assert team_id == "laa"
        return {"team_id": "laa", "name": "LAA", "league": "MLB", "season": 2025}

    def fake_fetch_lineup_candidates(_connection, team_id: str, limit: int = 15):
        assert team_id == "laa"
        assert limit == 3
        return [
            {
                "hitter_id": "hitter_1",
                "hitter_name": "Neto, Zach",
                "batting_side": "R",
                "plate_appearance_count": 19,
                "most_recent_game_date": "2025-06-04",
            },
            {
                "hitter_id": "hitter_2",
                "hitter_name": "Schanuel, Nolan",
                "batting_side": "L",
                "plate_appearance_count": 19,
                "most_recent_game_date": "2025-06-04",
            },
            {
                "hitter_id": "hitter_3",
                "hitter_name": "Ward, Taylor",
                "batting_side": "R",
                "plate_appearance_count": 18,
                "most_recent_game_date": "2025-06-04",
            },
        ]

    monkeypatch.setattr(main, "get_connection", fake_database_connection)
    monkeypatch.setattr(main, "fetch_pitcher_candidates", fake_fetch_pitcher_candidates)
    monkeypatch.setattr(main, "fetch_pitcher_candidate", fake_fetch_pitcher_candidate)
    monkeypatch.setattr(main, "fetch_team", fake_fetch_team)
    monkeypatch.setattr(main, "fetch_lineup_candidates", fake_fetch_lineup_candidates)

    client = TestClient(main.app)
    pitchers_response = client.get("/pitchers?limit=10&search=pitcher_123")
    assert pitchers_response.status_code == 200
    assert pitchers_response.json()[0]["pitcher_id"] == "pitcher_123"

    draft_response = client.post(
        "/matchups/draft",
        json={"pitcher_id": "pitcher_123", "opponent_team_id": "laa", "lineup_size": 3},
    )
    assert draft_response.status_code == 200
    body = draft_response.json()
    assert body["pitcher"]["pitcher_name"] == "Pitcher Example"
    assert body["opponent_team"]["team_id"] == "laa"
    assert len(body["lineup"]) == 3
    assert body["matchup_request"]["lineup"][0]["lineup_spot"] == 1


def test_live_roster_and_schedule_endpoints(monkeypatch) -> None:
    def fake_fetch_team_roster(team_id: str, season: int, roster_type: str = "active"):
        assert team_id == "laa"
        assert season == 2025
        assert roster_type == "active"
        return [
            {
                "team_id": "laa",
                "mlb_team_id": 108,
                "player_id": 687263,
                "full_name": "Zach Neto",
                "jersey_number": "9",
                "position": "SS",
                "status": "Active",
            }
        ]

    def fake_fetch_team_schedule(team_id: str, start_date: str, end_date: str):
        assert team_id == "laa"
        assert start_date == "2025-06-01"
        assert end_date == "2025-06-04"
        return [
            {
                "game_id": 777001,
                "game_date": "2025-06-04",
                "game_datetime": "2025-06-04T23:07:00Z",
                "home_team_id": "laa",
                "home_team_name": "Los Angeles Angels",
                "away_team_id": "bos",
                "away_team_name": "Boston Red Sox",
                "home_probable_pitcher_id": 123,
                "home_probable_pitcher_name": "Pitcher Home",
                "away_probable_pitcher_id": 456,
                "away_probable_pitcher_name": "Pitcher Away",
                "status": "Final",
            }
        ]

    monkeypatch.setattr(main, "fetch_team_roster", fake_fetch_team_roster)
    monkeypatch.setattr(main, "fetch_team_schedule", fake_fetch_team_schedule)

    client = TestClient(main.app)
    roster_response = client.get("/live/teams/laa/roster?season=2025&roster_type=active")
    assert roster_response.status_code == 200
    assert roster_response.json()[0]["full_name"] == "Zach Neto"

    schedule_response = client.get("/live/schedule?team_id=laa&start_date=2025-06-01&end_date=2025-06-04")
    assert schedule_response.status_code == 200
    assert schedule_response.json()[0]["home_probable_pitcher_name"] == "Pitcher Home"


def test_smart_matchup_draft_endpoint(monkeypatch) -> None:
    @contextmanager
    def fake_database_connection():
        yield object()

    def fake_fetch_team_schedule(team_id: str, start_date: str, end_date: str):
        assert team_id == "laa"
        assert start_date == "2025-06-03"
        assert end_date == "2025-06-03"
        return [
            {
                "game_id": 777667,
                "game_date": "2025-06-03",
                "game_datetime": "2025-06-03T23:10:00Z",
                "home_team_id": "bos",
                "home_team_name": "Boston Red Sox",
                "away_team_id": "laa",
                "away_team_name": "Los Angeles Angels",
                "home_probable_pitcher_id": 678394,
                "home_probable_pitcher_name": "Brayan Bello",
                "away_probable_pitcher_id": 579328,
                "away_probable_pitcher_name": "Yusei Kikuchi",
                "status": "Final",
            }
        ]

    def fake_fetch_team(_connection, team_id: str):
        return {"team_id": team_id, "name": team_id.upper(), "league": "MLB", "season": 2025}

    def fake_fetch_lineup_candidates(_connection, team_id: str, limit: int = 15):
        assert team_id == "laa"
        assert limit == 3
        return [
            {
                "hitter_id": "hitter_1",
                "hitter_name": "Neto, Zach",
                "batting_side": "R",
                "plate_appearance_count": 19,
                "most_recent_game_date": "2025-06-04",
            },
            {
                "hitter_id": "hitter_2",
                "hitter_name": "Schanuel, Nolan",
                "batting_side": "L",
                "plate_appearance_count": 19,
                "most_recent_game_date": "2025-06-04",
            },
            {
                "hitter_id": "hitter_3",
                "hitter_name": "Ward, Taylor",
                "batting_side": "R",
                "plate_appearance_count": 18,
                "most_recent_game_date": "2025-06-04",
            },
        ]

    def fake_fetch_player_by_mlbam_id(_connection, mlbam_id: int):
        assert mlbam_id == 678394
        return {
            "player_id": "pitcher_678394",
            "name": "Brayan Bello",
            "bats": "R",
            "throws": "R",
            "primary_role": "pitcher",
        }

    monkeypatch.setattr(main, "get_connection", fake_database_connection)
    monkeypatch.setattr(main, "fetch_team_schedule", fake_fetch_team_schedule)
    monkeypatch.setattr(main, "fetch_team", fake_fetch_team)
    monkeypatch.setattr(main, "fetch_lineup_candidates", fake_fetch_lineup_candidates)
    monkeypatch.setattr(main, "fetch_player_by_mlbam_id", fake_fetch_player_by_mlbam_id)

    client = TestClient(main.app)
    response = client.post(
        "/matchups/smart-draft",
        json={"team_id": "laa", "game_date": "2025-06-03", "lineup_size": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selected_game"]["game_id"] == 777667
    assert body["pitcher"]["pitcher_name"] == "Brayan Bello"
    assert body["opponent_team"]["team_id"] == "bos"
    assert len(body["lineup"]) == 3
    assert body["matchup_request"]["pitcher_id"] == "pitcher_678394"


def test_prepare_matchup_endpoint(monkeypatch) -> None:
    def fake_smart_draft_matchup(request):
        assert request.team_id == "laa"
        assert request.game_date == "2025-06-03"
        return main.SmartMatchupDraftResponse.model_validate(
            {
                "selected_game": {
                    "game_id": 777667,
                    "game_date": "2025-06-03",
                    "game_datetime": "2025-06-03T23:10:00Z",
                    "home_team_id": "bos",
                    "home_team_name": "Boston Red Sox",
                    "away_team_id": "laa",
                    "away_team_name": "Los Angeles Angels",
                    "home_probable_pitcher_id": 678394,
                    "home_probable_pitcher_name": "Brayan Bello",
                    "away_probable_pitcher_id": 579328,
                    "away_probable_pitcher_name": "Yusei Kikuchi",
                    "status": "Final",
                },
                "opponent_team": {"team_id": "bos", "name": "BOS", "league": "MLB", "season": 2025},
                "pitcher": {
                    "pitcher_id": "pitcher_678394",
                    "pitcher_name": "Brayan Bello",
                    "throws": "R",
                    "pitch_count": 0,
                    "most_recent_game_date": "2025-06-03",
                },
                "lineup": [
                    {
                        "hitter_id": "hitter_1",
                        "hitter_name": "Neto, Zach",
                        "batting_side": "R",
                        "plate_appearance_count": 19,
                        "most_recent_game_date": "2025-06-04",
                    },
                    {
                        "hitter_id": "hitter_2",
                        "hitter_name": "Schanuel, Nolan",
                        "batting_side": "L",
                        "plate_appearance_count": 18,
                        "most_recent_game_date": "2025-06-04",
                    }
                ],
                "matchup_request": {
                    "pitcher_id": "pitcher_678394",
                    "pitcher_name": "Brayan Bello",
                    "opponent_team_id": "bos",
                    "lineup": [
                        {
                            "hitter_id": "hitter_1",
                            "hitter_name": "Neto, Zach",
                            "batting_side": "R",
                            "lineup_spot": 1,
                        },
                        {
                            "hitter_id": "hitter_2",
                            "hitter_name": "Schanuel, Nolan",
                            "batting_side": "L",
                            "lineup_spot": 2,
                        }
                    ],
                    "manual_pitch_mix_adjustments": {},
                },
                "notes": ["drafted"],
            }
        )

    def fake_create_matchup(request):
        assert request.pitcher_id == "pitcher_678394"
        assert request.manual_pitch_mix_adjustments == {"ff": 0.55, "sl": 0.45}
        assert [hitter.hitter_id for hitter in request.lineup] == ["hitter_2", "hitter_1"]
        assert request.lineup[0].lineup_spot == 1
        assert request.reliever_id == "pitcher_relief_9"
        assert request.reliever_name == "Reliever Example"
        assert request.reliever_entry_batter_number == 20
        assert request.reliever_entry_inning == 7
        return main.MatchupResponse.model_validate(
            {
                "request_id": "11111111-1111-1111-1111-111111111111",
                "status": "simulated",
                "created_at": "2025-06-03T23:10:00Z",
                "overview": {
                    "expected_k_rate": 0.24,
                    "expected_bb_rate": 0.08,
                    "expected_bip_rate": 0.68,
                    "expected_hard_hit_rate": 0.34,
                    "estimated_run_value": 0.12,
                    "summary": "prepared",
                },
                "hitter_projections": [],
                "simulation": {
                    "iteration_count": 500,
                    "runs_scored": {"mean": 4.0, "p10": 1.0, "p50": 4.0, "p90": 8.0},
                    "hits": {"mean": 8.0, "p10": 5.0, "p50": 8.0, "p90": 12.0},
                    "home_runs": {"mean": 1.0, "p10": 0.0, "p50": 1.0, "p90": 2.0},
                    "plate_appearances": {"mean": 39.0, "p10": 33.0, "p50": 39.0, "p90": 46.0},
                    "strikeouts": {"mean": 8.0, "p10": 5.0, "p50": 8.0, "p90": 11.0},
                    "walks": {"mean": 3.0, "p10": 1.0, "p50": 3.0, "p90": 6.0},
                    "balls_in_play": {"mean": 25.0, "p10": 20.0, "p50": 25.0, "p90": 30.0},
                    "hard_hit_balls": {"mean": 5.0, "p10": 2.0, "p50": 5.0, "p90": 8.0},
                    "reliever_inherited_runners": {"mean": 0.6, "p10": 0.0, "p50": 0.0, "p90": 2.0},
                    "reliever_inherited_runners_scored": {"mean": 0.2, "p10": 0.0, "p50": 0.0, "p90": 1.0},
                    "run_value": {"mean": 0.8, "p10": -0.2, "p50": 0.8, "p90": 1.9},
                },
                "next_step": "done",
            }
        )

    monkeypatch.setattr(main, "smart_draft_matchup", fake_smart_draft_matchup)
    monkeypatch.setattr(main, "create_matchup", fake_create_matchup)

    client = TestClient(main.app)
    response = client.post(
        "/matchups/prepare",
        json={
            "team_id": "laa",
            "game_date": "2025-06-03",
            "lineup_size": 2,
            "lineup_override": [
                {
                    "hitter_id": "hitter_2",
                    "hitter_name": "Schanuel, Nolan",
                    "batting_side": "L",
                    "lineup_spot": 1,
                },
                {
                    "hitter_id": "hitter_1",
                    "hitter_name": "Neto, Zach",
                    "batting_side": "R",
                    "lineup_spot": 2,
                },
            ],
            "reliever_id": "pitcher_relief_9",
            "reliever_name": "Reliever Example",
            "reliever_entry_batter_number": 20,
            "reliever_entry_inning": 7,
            "manual_pitch_mix_adjustments": {"ff": 0.55, "sl": 0.45},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["pitcher"]["pitcher_name"] == "Brayan Bello"
    assert body["draft"]["lineup"][0]["hitter_id"] == "hitter_2"
    assert body["matchup"]["status"] == "simulated"
    assert any("Late-game reliever handoff enabled" in note for note in body["notes"])
    assert any("Applied manual pitch-mix overrides" in note for note in body["notes"])
