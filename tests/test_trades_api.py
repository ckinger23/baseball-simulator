from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from apps.api import main


@contextmanager
def fake_database_connection():
    yield object()


def fake_schedule_games():
    return [
        {
            "game_id": 900001,
            "game_date": "2026-07-17",
            "game_datetime": "2026-07-17T23:10:00Z",
            "home_team_id": "laa",
            "home_team_name": "Los Angeles Angels",
            "away_team_id": "bos",
            "away_team_name": "Boston Red Sox",
            "home_probable_pitcher_id": 111,
            "home_probable_pitcher_name": "Home Starter",
            "away_probable_pitcher_id": 678394,
            "away_probable_pitcher_name": "Brayan Bello",
            "status": "Scheduled",
        },
        {
            "game_id": 900002,
            "game_date": "2026-07-18",
            "game_datetime": "2026-07-18T23:10:00Z",
            "home_team_id": "laa",
            "home_team_name": "Los Angeles Angels",
            "away_team_id": "bos",
            "away_team_name": "Boston Red Sox",
            "home_probable_pitcher_id": 111,
            "home_probable_pitcher_name": "Home Starter",
            "away_probable_pitcher_id": 678395,
            "away_probable_pitcher_name": "Second Starter",
            "status": "Scheduled",
        },
    ]


def fake_lineup_candidates():
    return [
        {
            "hitter_id": "hitter_1",
            "hitter_name": "Leadoff, Larry",
            "batting_side": "L",
            "plate_appearance_count": 30,
            "most_recent_game_date": "2026-07-15",
        },
        {
            "hitter_id": "hitter_2",
            "hitter_name": "Displaced, Dave",
            "batting_side": "R",
            "plate_appearance_count": 28,
            "most_recent_game_date": "2026-07-15",
        },
        {
            "hitter_id": "hitter_3",
            "hitter_name": "Slugger, Sam",
            "batting_side": "R",
            "plate_appearance_count": 26,
            "most_recent_game_date": "2026-07-15",
        },
    ]


def projection_for(hitter_id: str, hitter_name: str) -> dict[str, object]:
    home_run_rate = 0.25 if hitter_id == "hitter_9" else 0.02
    return {
        "hitter_id": hitter_id,
        "hitter_name": hitter_name,
        "pitch_type_focus": "ff",
        "swing_rate": 0.47,
        "whiff_rate_on_swing": 0.24,
        "in_play_rate_on_swing": 0.41,
        "hard_hit_rate_on_contact": 0.35,
        "estimated_k_rate": 0.22,
        "estimated_bb_rate": 0.08,
        "estimated_bip_rate": 0.65,
        "single_rate": 0.15,
        "double_rate": 0.05,
        "triple_rate": 0.005,
        "home_run_rate": home_run_rate,
        "out_in_play_rate": 0.45,
        "estimated_run_value": 0.1,
    }


def apply_trade_monkeypatches(monkeypatch) -> None:
    def fake_fetch_team_schedule(team_id: str, start_date: str, end_date: str):
        games = fake_schedule_games()
        return [game for game in games if start_date <= game["game_date"] <= end_date]

    def fake_fetch_team(_connection, team_id: str):
        return {"team_id": team_id, "name": team_id.upper(), "league": "MLB", "season": 2026}

    def fake_fetch_lineup_candidates(_connection, team_id: str, limit: int = 15):
        return fake_lineup_candidates()[:limit]

    def fake_fetch_player_by_mlbam_id(_connection, mlbam_id: int):
        return {
            "player_id": f"pitcher_{mlbam_id}",
            "name": "Opposing Starter",
            "bats": "R",
            "throws": "R",
            "primary_role": "pitcher",
        }

    def fake_score_hitter_projection(**kwargs):
        hitter = kwargs["hitter"]
        return projection_for(str(hitter["hitter_id"]), str(hitter["hitter_name"]))

    monkeypatch.setattr(main, "get_connection", fake_database_connection)
    monkeypatch.setattr(main, "fetch_team_schedule", fake_fetch_team_schedule)
    monkeypatch.setattr(main, "fetch_team", fake_fetch_team)
    monkeypatch.setattr(main, "fetch_lineup_candidates", fake_fetch_lineup_candidates)
    monkeypatch.setattr(main, "fetch_player_by_mlbam_id", fake_fetch_player_by_mlbam_id)
    monkeypatch.setattr(main, "fetch_latest_pitcher_form", lambda _connection, _pitcher_id: None)
    monkeypatch.setattr(main, "fetch_pitcher_hand", lambda _connection, _pitcher_id: "R")
    monkeypatch.setattr(main, "fetch_hitter_profiles", lambda _connection, _ids, split_key: {})
    monkeypatch.setattr(main, "load_baseline_artifacts", lambda: None)
    monkeypatch.setattr(main, "score_hitter_projection", fake_score_hitter_projection)


def trade_request_body(**overrides) -> dict[str, object]:
    body: dict[str, object] = {
        "team_id": "laa",
        "incoming_hitter": {
            "hitter_id": "hitter_9",
            "hitter_name": "Acquired, Andy",
            "batting_side": "L",
        },
        "displaced_hitter_id": "hitter_2",
        "start_date": "2026-07-17",
        "end_date": "2026-07-18",
        "iteration_count": 200,
        "lineup_size": 3,
    }
    body.update(overrides)
    return body


def test_trade_evaluation_returns_per_game_and_window_deltas(monkeypatch) -> None:
    apply_trade_monkeypatches(monkeypatch)

    client = TestClient(main.app)
    response = client.post("/trades/evaluate", json=trade_request_body())

    assert response.status_code == 200
    body = response.json()

    assert body["team_id"] == "laa"
    assert body["games_evaluated"] == 2
    assert body["iteration_count"] == 200
    assert body["incoming_hitter"]["hitter_id"] == "hitter_9"
    assert body["displaced_hitter"]["hitter_id"] == "hitter_2"
    assert body["displaced_hitter"]["hitter_name"] == "Displaced, Dave"

    assert len(body["game_deltas"]) == 2
    for game_delta in body["game_deltas"]:
        assert game_delta["opponent_team_id"] == "bos"
        assert game_delta["runs_delta"]["p10"] <= game_delta["runs_delta"]["p50"] <= game_delta["runs_delta"]["p90"]
        assert game_delta["runs_delta"]["mean_ci_low"] <= game_delta["runs_delta"]["mean_ci_high"]
        # The incoming hitter is a major upgrade, so each game should add runs.
        assert game_delta["variant_runs_mean"] > game_delta["baseline_runs_mean"]

    assert body["window_runs_delta"]["mean"] > 0
    # A 0.02 -> 0.25 HR-rate upgrade should be clearly distinguishable from zero.
    assert body["window_runs_delta"]["mean_ci_low"] > 0
    assert body["runs_delta_per_game"] == round(body["window_runs_delta"]["mean"] / 2, 4)
    assert any("common random numbers" in note for note in body["notes"])


def test_trade_evaluation_respects_max_games(monkeypatch) -> None:
    apply_trade_monkeypatches(monkeypatch)

    client = TestClient(main.app)
    response = client.post("/trades/evaluate", json=trade_request_body(max_games=1))

    assert response.status_code == 200
    body = response.json()
    assert body["games_evaluated"] == 1
    assert body["game_deltas"][0]["game_id"] == 900001


def test_trade_evaluation_rejects_displaced_hitter_not_in_lineup(monkeypatch) -> None:
    apply_trade_monkeypatches(monkeypatch)

    client = TestClient(main.app)
    response = client.post("/trades/evaluate", json=trade_request_body(displaced_hitter_id="hitter_404"))

    assert response.status_code == 422
    assert "hitter_404 is not in the projected lineup" in response.json()["detail"]


def test_trade_evaluation_rejects_incoming_hitter_already_in_lineup(monkeypatch) -> None:
    apply_trade_monkeypatches(monkeypatch)

    client = TestClient(main.app)
    body = trade_request_body()
    body["incoming_hitter"] = {"hitter_id": "hitter_3", "hitter_name": "Slugger, Sam", "batting_side": "R"}
    response = client.post("/trades/evaluate", json=body)

    assert response.status_code == 422
    assert "hitter_3 is already in the projected lineup" in response.json()["detail"]


def test_trade_evaluation_returns_404_without_schedule_games(monkeypatch) -> None:
    apply_trade_monkeypatches(monkeypatch)

    client = TestClient(main.app)
    response = client.post(
        "/trades/evaluate",
        json=trade_request_body(start_date="2026-09-01", end_date="2026-09-02"),
    )

    assert response.status_code == 404
    assert "No live schedule games" in response.json()["detail"]
