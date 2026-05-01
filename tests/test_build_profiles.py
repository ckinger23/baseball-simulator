from __future__ import annotations

from datetime import date

from services.etl.build_profiles import build_hitter_tendency_profiles


def test_build_hitter_tendency_profiles_includes_recent_form() -> None:
    rows = [
        {
            "game_id": "g1",
            "pa_id": "g1_pa_1",
            "pitch_number": 1,
            "hitter_id": "h1",
            "pitcher_hand": "R",
            "pitch_type": "ff",
            "zone_bucket": "chase",
            "swing_flag": True,
            "whiff_flag": True,
            "in_play_flag": False,
            "hard_hit_flag": False,
        },
        {
            "game_id": "g2",
            "pa_id": "g2_pa_2",
            "pitch_number": 1,
            "hitter_id": "h1",
            "pitcher_hand": "R",
            "pitch_type": "ff",
            "zone_bucket": "heart",
            "swing_flag": True,
            "whiff_flag": False,
            "in_play_flag": True,
            "hard_hit_flag": True,
            "bb_type": "line_drive",
            "launch_speed": 102.0,
            "launch_angle": 24.0,
        },
    ]
    game_dates = {"g1": date(2025, 6, 1), "g2": date(2025, 6, 2)}

    profiles = build_hitter_tendency_profiles(rows, game_dates)

    assert len(profiles) == 1
    recent_form = profiles[0]["profile_json"]["recent_form"]
    assert recent_form["sample_pitch_count"] == 2
    assert recent_form["swing_rate"] == 1.0
    assert recent_form["chase_rate"] == 1.0
    assert recent_form["whiff_rate"] == 0.5
    assert recent_form["hard_hit_rate"] == 1.0
    assert recent_form["air_ball_rate"] == 1.0
    assert recent_form["barrel_proxy_rate"] == 1.0
