from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LineupHitter(BaseModel):
    hitter_id: str = Field(..., description="Canonical hitter identifier.")
    hitter_name: str
    batting_side: str = Field(..., description="L, R, or S.")
    lineup_spot: int = Field(..., ge=1, le=9)


class MatchupRequest(BaseModel):
    pitcher_id: str
    pitcher_name: str | None = None
    reliever_id: str | None = None
    reliever_name: str | None = None
    reliever_entry_batter_number: int | None = Field(default=None, ge=1, le=60)
    reliever_entry_inning: int | None = Field(default=None, ge=1, le=12)
    opponent_team_id: str
    form_window_start: str | None = None
    form_window_end: str | None = None
    lineup: list[LineupHitter]
    manual_pitch_mix_adjustments: dict[str, float] = Field(default_factory=dict)

    @property
    def lineup_left_handed_count(self) -> int:
        return sum(1 for hitter in self.lineup if hitter.batting_side == "L")

    @property
    def lineup_right_handed_count(self) -> int:
        return sum(1 for hitter in self.lineup if hitter.batting_side == "R")


class MatchupOverview(BaseModel):
    expected_k_rate: float
    expected_bb_rate: float
    expected_bip_rate: float
    expected_hard_hit_rate: float
    estimated_run_value: float
    summary: str


class HitterProjection(BaseModel):
    hitter_id: str
    hitter_name: str
    pitch_type_focus: str
    swing_rate: float
    whiff_rate_on_swing: float
    in_play_rate_on_swing: float
    hard_hit_rate_on_contact: float
    estimated_k_rate: float
    estimated_bb_rate: float
    estimated_bip_rate: float
    single_rate: float
    double_rate: float
    triple_rate: float
    home_run_rate: float
    out_in_play_rate: float
    estimated_run_value: float


class DistributionSummary(BaseModel):
    mean: float
    p10: float
    p50: float
    p90: float


class SimulationSummary(BaseModel):
    iteration_count: int
    runs_scored: DistributionSummary
    hits: DistributionSummary
    home_runs: DistributionSummary
    plate_appearances: DistributionSummary
    strikeouts: DistributionSummary
    walks: DistributionSummary
    balls_in_play: DistributionSummary
    hard_hit_balls: DistributionSummary
    reliever_inherited_runners: DistributionSummary
    reliever_inherited_runners_scored: DistributionSummary
    run_value: DistributionSummary


class MatchupResponse(BaseModel):
    request_id: UUID
    status: str
    created_at: datetime
    overview: MatchupOverview
    hitter_projections: list[HitterProjection] = Field(default_factory=list)
    simulation: SimulationSummary | None = None
    next_step: str


class SavedMatchupSummary(BaseModel):
    request_id: UUID
    created_at: datetime
    status: str
    pitcher_id: str
    opponent_team_id: str
    model_version: str | None = None
    overview: MatchupOverview | None = None
    simulation: SimulationSummary | None = None


class MatchupComparisonRequest(BaseModel):
    request_ids: list[UUID] = Field(..., min_length=2, max_length=5)


class MatchupComparisonDelta(BaseModel):
    baseline_request_id: UUID
    comparison_request_id: UUID
    expected_k_rate_delta: float
    expected_bb_rate_delta: float
    runs_scored_mean_delta: float
    home_runs_mean_delta: float
    run_value_mean_delta: float


class MatchupComparisonResponse(BaseModel):
    matchups: list[SavedMatchupSummary]
    deltas: list[MatchupComparisonDelta]


class TeamSummary(BaseModel):
    team_id: str
    name: str
    league: str
    season: int


class LineupCandidate(BaseModel):
    hitter_id: str
    hitter_name: str
    batting_side: str | None = None
    plate_appearance_count: int
    most_recent_game_date: str | None = None


class PitcherCandidate(BaseModel):
    pitcher_id: str
    pitcher_name: str
    throws: str | None = None
    pitch_count: int
    most_recent_game_date: str | None = None


class MatchupDraftRequest(BaseModel):
    pitcher_id: str
    opponent_team_id: str
    lineup_size: int = Field(default=9, ge=1, le=9)


class MatchupDraftResponse(BaseModel):
    pitcher: PitcherCandidate
    opponent_team: TeamSummary
    lineup: list[LineupCandidate]
    matchup_request: MatchupRequest
    notes: list[str] = Field(default_factory=list)


class SmartMatchupDraftRequest(BaseModel):
    team_id: str
    game_date: str
    game_id: int | None = None
    lineup_size: int = Field(default=9, ge=1, le=9)


class SmartMatchupDraftResponse(BaseModel):
    selected_game: LiveScheduleGame
    opponent_team: TeamSummary
    pitcher: PitcherCandidate
    lineup: list[LineupCandidate]
    matchup_request: MatchupRequest
    notes: list[str] = Field(default_factory=list)


class PrepareMatchupRequest(BaseModel):
    team_id: str
    game_date: str
    game_id: int | None = None
    lineup_size: int = Field(default=9, ge=1, le=9)
    lineup_override: list[LineupHitter] = Field(default_factory=list)
    reliever_id: str | None = None
    reliever_name: str | None = None
    reliever_entry_batter_number: int | None = Field(default=None, ge=1, le=60)
    reliever_entry_inning: int | None = Field(default=None, ge=1, le=12)
    manual_pitch_mix_adjustments: dict[str, float] = Field(default_factory=dict)


class PrepareMatchupResponse(BaseModel):
    draft: SmartMatchupDraftResponse
    matchup: MatchupResponse
    notes: list[str] = Field(default_factory=list)


class LiveRosterPlayer(BaseModel):
    team_id: str
    mlb_team_id: int
    player_id: int | None = None
    full_name: str | None = None
    jersey_number: str | None = None
    position: str | None = None
    status: str | None = None


class LiveScheduleGame(BaseModel):
    game_id: int | None = None
    game_date: str | None = None
    game_datetime: str | None = None
    home_team_id: str | None = None
    home_team_name: str | None = None
    away_team_id: str | None = None
    away_team_name: str | None = None
    home_probable_pitcher_id: int | None = None
    home_probable_pitcher_name: str | None = None
    away_probable_pitcher_id: int | None = None
    away_probable_pitcher_name: str | None = None
    status: str | None = None


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
