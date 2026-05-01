from __future__ import annotations

from services.modeling.inference import BaselineArtifacts, score_hitter_projection


def test_score_hitter_projection_applies_calibration_adjustments() -> None:
    artifacts = BaselineArtifacts(
        swing={
            "global_positive_rate": 0.5,
            "segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.52}}},
                "by_zone_and_count": {"rates": {"zone_bucket=shadow|balls=0|strikes=1": {"positive_rate": 0.5}}},
                "by_matchup_and_pitch": {
                    "rates": {"pitcher_hand=R|hitter_side=L|pitch_type=ff": {"positive_rate": 0.48}}
                },
            },
            "calibration": {"global_multiplier": 0.9},
        },
        contact={
            "whiff_global_rate": 0.25,
            "in_play_global_rate": 0.42,
            "whiff_segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.28}}},
                "by_matchup": {"rates": {"pitcher_hand=R|hitter_side=L": {"positive_rate": 0.27}}},
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=ff": {"positive_rate": 0.26}}},
            },
            "in_play_segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.45}}},
                "by_matchup": {"rates": {"pitcher_hand=R|hitter_side=L": {"positive_rate": 0.44}}},
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=ff": {"positive_rate": 0.43}}},
            },
            "calibration": {
                "whiff": {"global_multiplier": 1.1},
                "in_play": {"global_multiplier": 0.85},
            },
        },
    )

    projection = score_hitter_projection(
        artifacts=artifacts,
        hitter={"hitter_id": "h1", "hitter_name": "Test Hitter", "batting_side": "L"},
        pitcher_hand="R",
        form_profile=None,
        hitter_profile=None,
        manual_pitch_mix_adjustments={"ff": 1.0},
    )

    assert round(projection["swing_rate"], 4) == 0.4432
    assert round(projection["whiff_rate_on_swing"], 4) == 0.2888
    assert round(projection["in_play_rate_on_swing"], 4) == 0.374


def test_score_hitter_projection_blends_direct_pa_outcomes() -> None:
    artifacts = BaselineArtifacts(
        swing={
            "global_positive_rate": 0.5,
            "segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.5}}},
                "by_zone_and_count": {"rates": {"zone_bucket=shadow|balls=0|strikes=1": {"positive_rate": 0.5}}},
                "by_matchup_and_pitch": {
                    "rates": {"pitcher_hand=R|hitter_side=R|pitch_type=ff": {"positive_rate": 0.5}}
                },
            },
            "calibration": {"global_multiplier": 1.0},
        },
        contact={
            "whiff_global_rate": 0.25,
            "in_play_global_rate": 0.42,
            "whiff_segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.25}}},
                "by_matchup": {"rates": {"pitcher_hand=R|hitter_side=R": {"positive_rate": 0.25}}},
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=ff": {"positive_rate": 0.25}}},
            },
            "in_play_segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.42}}},
                "by_matchup": {"rates": {"pitcher_hand=R|hitter_side=R": {"positive_rate": 0.42}}},
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=ff": {"positive_rate": 0.42}}},
            },
            "calibration": {
                "whiff": {"global_multiplier": 1.0},
                "in_play": {"global_multiplier": 1.0},
            },
        },
        pa_outcomes={
            "outcomes": ["walk", "strikeout", "single", "double", "triple", "home_run", "ball_in_play_out"],
            "global_outcome_rates": {
                "walk": 0.08,
                "strikeout": 0.21,
                "single": 0.16,
                "double": 0.05,
                "triple": 0.01,
                "home_run": 0.04,
                "ball_in_play_out": 0.45,
            },
            "segments": {
                "by_pitch_type": {
                    "rates": {
                        "pitch_type=ff": {
                            "outcome_rates": {
                                "walk": 0.09,
                                "strikeout": 0.2,
                                "single": 0.18,
                                "double": 0.06,
                                "triple": 0.01,
                                "home_run": 0.05,
                                "ball_in_play_out": 0.41,
                            }
                        }
                    }
                },
                "by_matchup": {
                    "rates": {
                        "pitcher_hand=R|hitter_side=R": {
                            "outcome_rates": {
                                "walk": 0.07,
                                "strikeout": 0.22,
                                "single": 0.17,
                                "double": 0.05,
                                "triple": 0.01,
                                "home_run": 0.04,
                                "ball_in_play_out": 0.44,
                            }
                        }
                    }
                },
                "by_count": {
                    "rates": {
                        "count_bucket=even": {
                            "outcome_rates": {
                                "walk": 0.08,
                                "strikeout": 0.21,
                                "single": 0.17,
                                "double": 0.05,
                                "triple": 0.01,
                                "home_run": 0.04,
                                "ball_in_play_out": 0.44,
                            }
                        }
                    }
                },
                "by_matchup_and_pitch": {
                    "rates": {
                        "pitcher_hand=R|hitter_side=R|pitch_type=ff": {
                            "outcome_rates": {
                                "walk": 0.06,
                                "strikeout": 0.23,
                                "single": 0.17,
                                "double": 0.06,
                                "triple": 0.01,
                                "home_run": 0.05,
                                "ball_in_play_out": 0.42,
                            }
                        }
                    }
                },
                "by_matchup_pitch_count": {
                    "rates": {
                        "pitcher_hand=R|hitter_side=R|pitch_type=ff|count_bucket=even": {
                            "outcome_rates": {
                                "walk": 0.07,
                                "strikeout": 0.22,
                                "single": 0.16,
                                "double": 0.06,
                                "triple": 0.01,
                                "home_run": 0.05,
                                "ball_in_play_out": 0.43,
                            }
                        }
                    }
                },
                "by_form_and_pitch": {
                    "rates": {
                        "pitcher_form_bucket=steady|pitch_type=ff": {
                            "outcome_rates": {
                                "walk": 0.08,
                                "strikeout": 0.21,
                                "single": 0.15,
                                "double": 0.05,
                                "triple": 0.01,
                                "home_run": 0.04,
                                "ball_in_play_out": 0.46,
                            }
                        }
                    }
                },
            },
            "calibration": {
                "walk": {"global_multiplier": 1.0},
                "strikeout": {"global_multiplier": 1.0},
                "single": {"global_multiplier": 1.0},
                "double": {"global_multiplier": 1.0},
                "triple": {"global_multiplier": 1.0},
                "home_run": {"global_multiplier": 1.0},
                "ball_in_play_out": {"global_multiplier": 1.0},
            },
        },
    )

    projection = score_hitter_projection(
        artifacts=artifacts,
        hitter={"hitter_id": "h2", "hitter_name": "Outcome Hitter", "batting_side": "R"},
        pitcher_hand="R",
        form_profile=None,
        hitter_profile=None,
        manual_pitch_mix_adjustments={"ff": 1.0},
    )

    total_probability = (
        projection["estimated_bb_rate"]
        + projection["estimated_k_rate"]
        + projection["single_rate"]
        + projection["double_rate"]
        + projection["triple_rate"]
        + projection["home_run_rate"]
        + projection["out_in_play_rate"]
    )
    assert abs(total_probability - 1.0) < 0.001
    assert projection["single_rate"] > 0.0
    assert projection["out_in_play_rate"] > projection["home_run_rate"]


def test_score_hitter_projection_uses_whiff_and_chase_buckets_for_strikeouts() -> None:
    artifacts = BaselineArtifacts(
        swing={
            "global_positive_rate": 0.5,
            "segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.5}}},
                "by_zone_and_count": {"rates": {"zone_bucket=shadow|balls=0|strikes=1": {"positive_rate": 0.5}}},
                "by_matchup_and_pitch": {
                    "rates": {"pitcher_hand=R|hitter_side=R|pitch_type=ff": {"positive_rate": 0.5}}
                },
            },
            "calibration": {"global_multiplier": 1.0},
        },
        contact={
            "whiff_global_rate": 0.25,
            "in_play_global_rate": 0.42,
            "whiff_segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.25}}},
                "by_matchup": {"rates": {"pitcher_hand=R|hitter_side=R": {"positive_rate": 0.25}}},
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=ff": {"positive_rate": 0.25}}},
            },
            "in_play_segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.42}}},
                "by_matchup": {"rates": {"pitcher_hand=R|hitter_side=R": {"positive_rate": 0.42}}},
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=ff": {"positive_rate": 0.42}}},
            },
            "calibration": {
                "whiff": {"global_multiplier": 1.0},
                "in_play": {"global_multiplier": 1.0},
            },
        },
        pa_outcomes={
            "outcomes": ["walk", "strikeout", "single", "double", "triple", "home_run", "ball_in_play_out"],
            "global_outcome_rates": {
                "walk": 0.08,
                "strikeout": 0.20,
                "single": 0.17,
                "double": 0.05,
                "triple": 0.01,
                "home_run": 0.03,
                "ball_in_play_out": 0.46,
            },
            "segments": {
                "by_pitch_type": {
                    "rates": {
                        "pitch_type=ff": {
                            "outcome_rates": {
                                "walk": 0.08,
                                "strikeout": 0.20,
                                "single": 0.17,
                                "double": 0.05,
                                "triple": 0.01,
                                "home_run": 0.03,
                                "ball_in_play_out": 0.46,
                            }
                        }
                    }
                },
                "by_whiff_buckets": {
                    "rates": {
                        "pitcher_whiff_bucket=bat_missing|hitter_whiff_bucket=swing_miss_prone|pitch_type=ff": {
                            "outcome_rates": {
                                "walk": 0.06,
                                "strikeout": 0.34,
                                "single": 0.13,
                                "double": 0.04,
                                "triple": 0.01,
                                "home_run": 0.02,
                                "ball_in_play_out": 0.40,
                            }
                        }
                    }
                },
                "by_strikeout_context": {
                    "rates": {
                        "count_bucket=two_strike|pitcher_whiff_bucket=bat_missing|hitter_whiff_bucket=swing_miss_prone": {
                            "outcome_rates": {
                                "walk": 0.04,
                                "strikeout": 0.42,
                                "single": 0.11,
                                "double": 0.03,
                                "triple": 0.01,
                                "home_run": 0.02,
                                "ball_in_play_out": 0.37,
                            }
                        }
                    }
                },
                "by_chase_context": {
                    "rates": {
                        "hitter_chase_bucket=aggressive|pitcher_hand=R|hitter_side=R": {
                            "outcome_rates": {
                                "walk": 0.05,
                                "strikeout": 0.30,
                                "single": 0.14,
                                "double": 0.05,
                                "triple": 0.01,
                                "home_run": 0.03,
                                "ball_in_play_out": 0.42,
                            }
                        }
                    }
                },
            },
            "calibration": {
                "walk": {"global_multiplier": 1.0},
                "strikeout": {"global_multiplier": 1.0},
                "single": {"global_multiplier": 1.0},
                "double": {"global_multiplier": 1.0},
                "triple": {"global_multiplier": 1.0},
                "home_run": {"global_multiplier": 1.0},
                "ball_in_play_out": {"global_multiplier": 1.0},
            },
        },
    )

    projection = score_hitter_projection(
        artifacts=artifacts,
        hitter={"hitter_id": "h3", "hitter_name": "Whiff Hitter", "batting_side": "R"},
        pitcher_hand="R",
        form_profile={
            "profile_json": {
                "overall_metrics": {"strikeout_rate": 0.31, "walk_rate": 0.06, "in_play_hard_hit_rate": 0.33},
                "whiff_rate_by_pitch_type": {"ff": 0.35},
            }
        },
        hitter_profile={
            "profile_json": {
                "whiff_rate_by_pitch_type": {"ff": 0.36},
                "chase_rate": 0.34,
                "swing_rate": 0.5,
                "damage_rate_by_pitch_type": {"ff": 0.32},
            }
        },
        manual_pitch_mix_adjustments={"ff": 0.7},
    )

    assert projection["estimated_k_rate"] > 0.26
    assert projection["estimated_k_rate"] > projection["estimated_bb_rate"]


def test_score_hitter_projection_supports_staged_pa_artifact() -> None:
    artifacts = BaselineArtifacts(
        swing={
            "global_positive_rate": 0.5,
            "segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.5}}},
                "by_zone_and_count": {"rates": {"zone_bucket=shadow|balls=0|strikes=1": {"positive_rate": 0.5}}},
                "by_matchup_and_pitch": {
                    "rates": {"pitcher_hand=R|hitter_side=R|pitch_type=ff": {"positive_rate": 0.5}}
                },
            },
            "calibration": {"global_multiplier": 1.0},
        },
        contact={
            "whiff_global_rate": 0.25,
            "in_play_global_rate": 0.42,
            "whiff_segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.25}}},
                "by_matchup": {"rates": {"pitcher_hand=R|hitter_side=R": {"positive_rate": 0.25}}},
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=ff": {"positive_rate": 0.42}}},
            },
            "in_play_segments": {
                "by_pitch_type": {"rates": {"pitch_type=ff": {"positive_rate": 0.42}}},
                "by_matchup": {"rates": {"pitcher_hand=R|hitter_side=R": {"positive_rate": 0.42}}},
                "by_zone_pitch": {"rates": {"zone_bucket=shadow|pitch_type=ff": {"positive_rate": 0.42}}},
            },
            "calibration": {"whiff": {"global_multiplier": 1.0}, "in_play": {"global_multiplier": 1.0}},
        },
        pa_outcomes={
            "stages": {
                "pa_stage": {
                    "outcomes": ["walk", "strikeout", "ball_in_play"],
                    "global_rates": {"walk": 0.08, "strikeout": 0.22, "ball_in_play": 0.70},
                    "segment_specs": {
                        "by_pitch_type": ["pitch_type"],
                        "by_matchup": ["pitcher_hand", "hitter_side"],
                    },
                    "segments": {
                        "by_pitch_type": {
                            "rates": {
                                "pitch_type=ff": {
                                    "sample_size": 100,
                                    "outcome_rates": {"walk": 0.07, "strikeout": 0.24, "ball_in_play": 0.69},
                                }
                            }
                        },
                        "by_matchup": {
                            "rates": {
                                "pitcher_hand=R|hitter_side=R": {
                                    "sample_size": 100,
                                    "outcome_rates": {"walk": 0.08, "strikeout": 0.23, "ball_in_play": 0.69},
                                }
                            }
                        },
                    },
                },
                "bip_hit_stage": {
                    "outcomes": ["hit", "ball_in_play_out"],
                    "global_rates": {"hit": 0.34, "ball_in_play_out": 0.66},
                    "segment_specs": {
                        "by_pitch_type": ["pitch_type"],
                        "by_damage_context": ["pitcher_contact_bucket", "hitter_damage_bucket", "pitch_type"],
                    },
                    "segments": {
                        "by_pitch_type": {
                            "rates": {
                                "pitch_type=ff": {
                                    "sample_size": 100,
                                    "outcome_rates": {"hit": 0.36, "ball_in_play_out": 0.64},
                                }
                            }
                        },
                        "by_damage_context": {
                            "rates": {
                                "pitcher_contact_bucket=average|hitter_damage_bucket=impact|pitch_type=ff": {
                                    "sample_size": 100,
                                    "outcome_rates": {"hit": 0.39, "ball_in_play_out": 0.61},
                                }
                            }
                        },
                    },
                },
                "hit_type_stage": {
                    "outcomes": ["single", "double", "triple", "home_run"],
                    "global_rates": {"single": 0.64, "double": 0.2, "triple": 0.02, "home_run": 0.14},
                    "segment_specs": {
                        "by_pitch_type": ["pitch_type"],
                        "by_damage_context": ["pitcher_contact_bucket", "hitter_damage_bucket", "pitch_type"],
                    },
                    "segments": {
                        "by_pitch_type": {
                            "rates": {
                                "pitch_type=ff": {
                                    "sample_size": 100,
                                    "outcome_rates": {"single": 0.61, "double": 0.2, "triple": 0.02, "home_run": 0.17},
                                }
                            }
                        },
                        "by_damage_context": {
                            "rates": {
                                "pitcher_contact_bucket=average|hitter_damage_bucket=impact|pitch_type=ff": {
                                    "sample_size": 100,
                                    "outcome_rates": {"single": 0.56, "double": 0.21, "triple": 0.02, "home_run": 0.21},
                                }
                            }
                        },
                    },
                },
            },
            "calibration": {
                "walk": {"global_multiplier": 1.0},
                "strikeout": {"global_multiplier": 1.0},
                "single": {"global_multiplier": 1.0},
                "double": {"global_multiplier": 1.0},
                "triple": {"global_multiplier": 1.0},
                "home_run": {"global_multiplier": 1.0},
                "ball_in_play_out": {"global_multiplier": 1.0},
            },
        },
    )

    projection = score_hitter_projection(
        artifacts=artifacts,
        hitter={"hitter_id": "h4", "hitter_name": "Staged Hitter", "batting_side": "R"},
        pitcher_hand="R",
        form_profile={"profile_json": {"overall_metrics": {"strikeout_rate": 0.24, "walk_rate": 0.07, "in_play_hard_hit_rate": 0.36}}},
        hitter_profile={
            "profile_json": {
                "damage_rate_by_pitch_type": {"ff": 0.45},
                "whiff_rate_by_pitch_type": {"ff": 0.28},
                "chase_rate": 0.27,
                "recent_form": {
                    "hard_hit_rate": 0.48,
                    "air_ball_rate": 0.61,
                    "barrel_proxy_rate": 0.16,
                },
            }
        },
        manual_pitch_mix_adjustments={"ff": 1.0},
    )

    total_probability = (
        projection["estimated_bb_rate"]
        + projection["estimated_k_rate"]
        + projection["single_rate"]
        + projection["double_rate"]
        + projection["triple_rate"]
        + projection["home_run_rate"]
        + projection["out_in_play_rate"]
    )
    assert abs(total_probability - 1.0) < 0.001
    assert projection["home_run_rate"] > 0.03
