from __future__ import annotations

import argparse
from pathlib import Path

from infrastructure.scripts.evaluate_model_windows import build_markdown_report, parse_window
from infrastructure.scripts.evaluate_pooled_pa_model import build_markdown_report as build_pooled_markdown_report
from services.modeling.train_pa_outcome_model import resolve_combined_holdout_game_ids, smoothed_outcome_rates


def test_parse_window_rejects_empty_label() -> None:
    try:
        parse_window("=data/processed")
    except argparse.ArgumentTypeError as exc:
        assert "cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected parse_window to reject empty labels")


def test_parse_window_resolves_relative_paths() -> None:
    label, path = parse_window("june=data/processed")

    assert label == "june"
    assert path == Path.cwd() / "data/processed"


def test_build_markdown_report_includes_window_notes() -> None:
    report = build_markdown_report(
        [
            {
                "label": "sample",
                "metrics": {
                    "swing": {
                        "predicted_rate": 0.45,
                        "observed_rate": 0.5,
                        "global_multiplier": 1.1111,
                        "brier_score": 0.24,
                    },
                    "contact": {
                        "whiff": {
                            "predicted_rate": 0.22,
                            "observed_rate": 0.25,
                            "global_multiplier": 1.1364,
                            "brier_score": 0.18,
                        },
                        "in_play": {
                            "predicted_rate": 0.37,
                            "observed_rate": 0.34,
                            "global_multiplier": 0.9189,
                            "brier_score": 0.21,
                        },
                    },
                    "pa_outcomes": {
                        "walk": {
                            "predicted_rate": 0.09,
                            "observed_rate": 0.08,
                            "global_multiplier": 0.8889,
                            "brier_score": 0.07,
                        },
                        "home_run": {
                            "predicted_rate": 0.03,
                            "observed_rate": 0.015,
                            "global_multiplier": 0.5,
                            "brier_score": 0.02,
                        },
                    },
                },
            }
        ]
    )

    assert "| sample | swing | 0.4500 | 0.5000 | 1.1111 | 0.2400 |" in report
    assert "`sample`" in report
    assert "home_run (0.50x)" in report


def test_resolve_combined_holdout_game_ids_allows_zero_fraction(tmp_path: Path) -> None:
    input_dir = tmp_path / "processed"
    input_dir.mkdir()
    (input_dir / "games.jsonl").write_text('{"game_id":"g1","game_date":"2025-06-01"}\n', encoding="utf-8")

    assert resolve_combined_holdout_game_ids([input_dir], 0.0) == set()


def test_build_pooled_markdown_report_includes_training_windows() -> None:
    report = build_pooled_markdown_report(
        {
            "train_labels": ["may_24_27", "june_01_04"],
            "evaluations": [
                {
                    "label": "june_08_11",
                    "metrics": {
                        "walk": {"predicted_rate": 0.08, "observed_rate": 0.07, "global_multiplier": 0.875, "brier_score": 0.06},
                        "strikeout": {"predicted_rate": 0.22, "observed_rate": 0.24, "global_multiplier": 1.0909, "brier_score": 0.16, "sample_size": 100},
                        "single": {"predicted_rate": 0.14, "observed_rate": 0.13, "global_multiplier": 0.9286, "brier_score": 0.11},
                        "double": {"predicted_rate": 0.04, "observed_rate": 0.05, "global_multiplier": 1.25, "brier_score": 0.04},
                        "home_run": {"predicted_rate": 0.03, "observed_rate": 0.02, "global_multiplier": 0.6667, "brier_score": 0.02},
                        "ball_in_play_out": {"predicted_rate": 0.49, "observed_rate": 0.49, "global_multiplier": 1.0, "brier_score": 0.24},
                    },
                }
            ],
        }
    )

    assert "`may_24_27`" in report
    assert "| june_08_11 | strikeout | 0.2200 | 0.2400 | 1.0909 | 0.1600 |" in report


def test_smoothed_outcome_rates_applies_stronger_home_run_prior() -> None:
    rates = smoothed_outcome_rates(
        counts={"single": 3, "home_run": 1},
        total=4,
        prior_rates={
            "walk": 0.08,
            "strikeout": 0.22,
            "single": 0.15,
            "double": 0.04,
            "triple": 0.01,
            "home_run": 0.02,
            "ball_in_play_out": 0.48,
        },
        outcomes=("walk", "strikeout", "single", "double", "triple", "home_run", "ball_in_play_out"),
    )

    assert abs(sum(rates.values()) - 1.0) < 0.001
    assert rates["home_run"] < 0.1
