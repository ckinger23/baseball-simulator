from __future__ import annotations

from services.etl.build_features import build_plate_appearance_record


def test_build_plate_appearance_record_sorts_pitch_rows_before_taking_result() -> None:
    rows = [
        {
            "game_pk": "123",
            "at_bat_number": "7",
            "pitch_number": "3",
            "pitcher": "111",
            "batter": "222",
            "inning": "5",
            "inning_topbot": "Top",
            "away_team": "LAA",
            "home_team": "BOS",
            "outs_when_up": "1",
            "events": "single",
            "description": "hit_into_play",
            "bat_score": "2",
            "post_bat_score": "3",
            "woba_value": "0.9",
            "delta_run_exp": "0.5",
        },
        {
            "game_pk": "123",
            "at_bat_number": "7",
            "pitch_number": "1",
            "pitcher": "111",
            "batter": "222",
            "inning": "5",
            "inning_topbot": "Top",
            "away_team": "LAA",
            "home_team": "BOS",
            "outs_when_up": "1",
            "events": "",
            "description": "ball",
            "bat_score": "2",
            "post_bat_score": "2",
            "woba_value": "",
            "delta_run_exp": "0.01",
        },
    ]

    record = build_plate_appearance_record(rows)

    assert record["result"] == "single"
    assert record["runs_scored"] == 1
