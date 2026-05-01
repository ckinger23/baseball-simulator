from __future__ import annotations

from services.simulation.engine import run_matchup_simulation


def test_simulation_tracks_runs_hits_and_plate_appearances() -> None:
    hitter_projections = [
        {
            "estimated_bb_rate": 0.1,
            "estimated_k_rate": 0.2,
            "single_rate": 0.16,
            "double_rate": 0.05,
            "triple_rate": 0.01,
            "home_run_rate": 0.04,
            "out_in_play_rate": 0.44,
            "hard_hit_rate_on_contact": 0.38,
        },
        {
            "estimated_bb_rate": 0.08,
            "estimated_k_rate": 0.22,
            "single_rate": 0.15,
            "double_rate": 0.04,
            "triple_rate": 0.01,
            "home_run_rate": 0.03,
            "out_in_play_rate": 0.47,
            "hard_hit_rate_on_contact": 0.34,
        },
    ]

    summary = run_matchup_simulation(hitter_projections, iteration_count=100, seed=7, innings=9)

    assert summary["iteration_count"] == 100
    assert summary["plate_appearances"]["mean"] >= 27.0
    assert summary["runs_scored"]["mean"] >= 0.0
    assert summary["hits"]["mean"] >= summary["home_runs"]["mean"]
    assert summary["balls_in_play"]["mean"] >= 0.0
    assert "reliever_inherited_runners" in summary
    assert "reliever_inherited_runners_scored" in summary


def test_simulation_supports_reliever_handoff() -> None:
    starter_projections = [
        {
            "estimated_bb_rate": 0.1,
            "estimated_k_rate": 0.18,
            "single_rate": 0.18,
            "double_rate": 0.06,
            "triple_rate": 0.01,
            "home_run_rate": 0.05,
            "out_in_play_rate": 0.42,
            "hard_hit_rate_on_contact": 0.42,
        }
        for _ in range(3)
    ]
    reliever_projections = [
        {
            "estimated_bb_rate": 0.07,
            "estimated_k_rate": 0.28,
            "single_rate": 0.14,
            "double_rate": 0.04,
            "triple_rate": 0.01,
            "home_run_rate": 0.03,
            "out_in_play_rate": 0.43,
            "hard_hit_rate_on_contact": 0.31,
        }
        for _ in range(3)
    ]

    starter_only = run_matchup_simulation(starter_projections, iteration_count=150, seed=11, innings=9)
    with_reliever = run_matchup_simulation(
        starter_projections,
        reliever_hitter_projections=reliever_projections,
        reliever_entry_batter_number=10,
        reliever_entry_inning=5,
        iteration_count=150,
        seed=11,
        innings=9,
    )

    assert with_reliever["strikeouts"]["mean"] >= starter_only["strikeouts"]["mean"]
    assert with_reliever["runs_scored"]["mean"] <= starter_only["runs_scored"]["mean"]
    assert with_reliever["reliever_inherited_runners"]["mean"] >= 0.0
