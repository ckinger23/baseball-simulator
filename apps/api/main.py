from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4, uuid5, NAMESPACE_URL

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.api.repository import (
    fetch_bullpen_candidates,
    fetch_hitter_profiles,
    fetch_latest_pitcher_form,
    fetch_pitcher_candidate,
    fetch_pitcher_candidates,
    fetch_pitcher_hand,
    fetch_lineup_candidates,
    fetch_player_by_mlbam_id,
    fetch_recent_saved_matchups,
    fetch_saved_matchup,
    fetch_team,
    fetch_teams,
    get_connection,
    insert_matchup_request,
    insert_simulation_run,
)
from packages.shared_types.matchups import (
    HealthResponse,
    HitterProjection,
    LineupCandidate,
    LiveRosterPlayer,
    LiveScheduleGame,
    MatchupDraftRequest,
    MatchupDraftResponse,
    MatchupComparisonDelta,
    MatchupComparisonRequest,
    MatchupComparisonResponse,
    MatchupOverview,
    MatchupRequest,
    MatchupResponse,
    PitcherCandidate,
    PrepareMatchupRequest,
    PrepareMatchupResponse,
    SavedMatchupSummary,
    SmartMatchupDraftRequest,
    SmartMatchupDraftResponse,
    SimulationSummary,
    TeamSummary,
    TradeDeltaSummary,
    TradeEvaluationRequest,
    TradeEvaluationResponse,
    TradeGameDelta,
    TradeHitter,
)
from services.external.mlb_stats_api import fetch_team_roster, fetch_team_schedule
from services.modeling.inference import load_baseline_artifacts, score_hitter_projection
from services.simulation.engine import run_matchup_simulation
from services.trades.evaluator import (
    aggregate_window_deltas,
    build_variant_lineup,
    paired_delta_samples,
    summarize_delta,
)

app = FastAPI(
    title="Baseball Matchup Simulator API",
    version="0.1.0",
    description="Initial API scaffold for matchup creation and report retrieval.",
)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
STATIC_DIR = WEB_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(UTC))


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


def average_projection_metric(hitter_projections: list[dict[str, object]], key: str, fallback: float) -> float:
    values = [
        float(projection[key])
        for projection in hitter_projections
        if isinstance(projection.get(key), (int, float))
    ]
    if not values:
        return fallback
    return round(sum(values) / len(values), 4)


def build_matchup_request_from_candidates(
    pitcher_id: str,
    pitcher_name: str,
    opponent_team_id: str,
    lineup_models: list[LineupCandidate],
) -> MatchupRequest:
    return MatchupRequest(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher_name,
        opponent_team_id=opponent_team_id,
        lineup=[
            {
                "hitter_id": candidate.hitter_id,
                "hitter_name": candidate.hitter_name,
                "batting_side": candidate.batting_side or "R",
                "lineup_spot": index + 1,
            }
            for index, candidate in enumerate(lineup_models)
        ],
    )


def apply_lineup_override_to_draft(
    draft: SmartMatchupDraftResponse,
    lineup_override: list[dict[str, object]] | list[LineupCandidate],
) -> SmartMatchupDraftResponse:
    lineup_by_id = {candidate.hitter_id: candidate for candidate in draft.lineup}
    ordered_candidates: list[LineupCandidate] = []

    for index, hitter in enumerate(lineup_override):
        if isinstance(hitter, LineupCandidate):
            hitter_id = hitter.hitter_id
            hitter_name = hitter.hitter_name
            batting_side = hitter.batting_side
        else:
            hitter_id = str(hitter["hitter_id"])
            hitter_name = str(hitter["hitter_name"])
            batting_side = str(hitter.get("batting_side") or "R")

        if hitter_id in lineup_by_id:
            candidate = lineup_by_id[hitter_id]
            ordered_candidates.append(
                LineupCandidate(
                    hitter_id=candidate.hitter_id,
                    hitter_name=hitter_name,
                    batting_side=batting_side,
                    plate_appearance_count=candidate.plate_appearance_count,
                    most_recent_game_date=candidate.most_recent_game_date,
                )
            )
        else:
            ordered_candidates.append(
                LineupCandidate(
                    hitter_id=hitter_id,
                    hitter_name=hitter_name,
                    batting_side=batting_side,
                    plate_appearance_count=0,
                    most_recent_game_date=None,
                )
            )

    matchup_request = MatchupRequest(
        pitcher_id=draft.matchup_request.pitcher_id,
        pitcher_name=draft.matchup_request.pitcher_name,
        opponent_team_id=draft.matchup_request.opponent_team_id,
        form_window_start=draft.matchup_request.form_window_start,
        form_window_end=draft.matchup_request.form_window_end,
        lineup=[
            {
                "hitter_id": candidate.hitter_id,
                "hitter_name": candidate.hitter_name,
                "batting_side": candidate.batting_side or "R",
                "lineup_spot": index + 1,
            }
            for index, candidate in enumerate(ordered_candidates)
        ],
        manual_pitch_mix_adjustments=draft.matchup_request.manual_pitch_mix_adjustments,
    )

    notes = [note for note in draft.notes if "Applied a custom lineup override" not in note]
    notes.append(f"Applied a custom lineup override with {len(ordered_candidates)} hitters before simulation.")

    return SmartMatchupDraftResponse(
        selected_game=draft.selected_game,
        opponent_team=draft.opponent_team,
        pitcher=draft.pitcher,
        lineup=ordered_candidates,
        matchup_request=matchup_request,
        notes=notes,
    )


def build_saved_matchup_summary(saved_matchup: dict[str, object]) -> SavedMatchupSummary:
    result_json = saved_matchup.get("result_json")
    overview = None
    simulation = None
    if isinstance(result_json, dict):
        raw_overview = result_json.get("overview")
        raw_simulation = result_json.get("simulation")
        if isinstance(raw_overview, dict):
            overview = MatchupOverview.model_validate(raw_overview)
        if isinstance(raw_simulation, dict):
            simulation = SimulationSummary.model_validate(raw_simulation)

    return SavedMatchupSummary(
        request_id=saved_matchup["request_id"],
        created_at=saved_matchup["created_at"],
        status=saved_matchup["status"],
        pitcher_id=saved_matchup["pitcher_id"],
        opponent_team_id=saved_matchup["opponent_team_id"],
        model_version=saved_matchup.get("model_version"),
        overview=overview,
        simulation=simulation,
    )


def require_database_connection() -> object:
    context = get_connection()
    connection = context.__enter__()
    if connection is None:
        context.__exit__(None, None, None)
        raise HTTPException(status_code=503, detail="DATABASE_URL is required for persisted matchup retrieval.")
    return context, connection


@app.get("/matchups", response_model=list[SavedMatchupSummary])
def list_matchups(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[SavedMatchupSummary]:
    context, connection = require_database_connection()
    try:
        saved_matchups = fetch_recent_saved_matchups(connection, limit=limit)
        return [build_saved_matchup_summary(item) for item in saved_matchups]
    finally:
        context.__exit__(None, None, None)


@app.get("/teams", response_model=list[TeamSummary])
def list_teams(
    season: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TeamSummary]:
    context, connection = require_database_connection()
    try:
        teams = fetch_teams(connection, season=season, limit=limit)
        return [TeamSummary.model_validate(team) for team in teams]
    finally:
        context.__exit__(None, None, None)


@app.get("/teams/{team_id}/lineup-candidates", response_model=list[LineupCandidate])
def list_lineup_candidates(
    team_id: str,
    limit: Annotated[int, Query(ge=1, le=40)] = 15,
) -> list[LineupCandidate]:
    context, connection = require_database_connection()
    try:
        candidates = fetch_lineup_candidates(connection, team_id=team_id, limit=limit)
        if not candidates:
            raise HTTPException(status_code=404, detail=f"No lineup candidates were found for team {team_id}.")
        return [LineupCandidate.model_validate(candidate) for candidate in candidates]
    finally:
        context.__exit__(None, None, None)


@app.get("/pitchers", response_model=list[PitcherCandidate])
def list_pitchers(
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    search: Annotated[str | None, Query()] = None,
) -> list[PitcherCandidate]:
    context, connection = require_database_connection()
    try:
        pitchers = fetch_pitcher_candidates(connection, limit=limit, search=search)
        return [PitcherCandidate.model_validate(pitcher) for pitcher in pitchers]
    finally:
        context.__exit__(None, None, None)


@app.get("/teams/{team_id}/bullpen-candidates", response_model=list[PitcherCandidate])
def list_bullpen_candidates(
    team_id: str,
    limit: Annotated[int, Query(ge=1, le=40)] = 10,
) -> list[PitcherCandidate]:
    context, connection = require_database_connection()
    try:
        candidates = fetch_bullpen_candidates(connection, team_id=team_id, limit=limit)
        if not candidates:
            raise HTTPException(status_code=404, detail=f"No bullpen candidates were found for team {team_id}.")
        return [PitcherCandidate.model_validate(candidate) for candidate in candidates]
    finally:
        context.__exit__(None, None, None)


@app.get("/live/teams/{team_id}/roster", response_model=list[LiveRosterPlayer])
def get_live_team_roster(
    team_id: str,
    season: Annotated[int, Query(ge=1900, le=2100)] = 2025,
    roster_type: Annotated[str, Query()] = "active",
) -> list[LiveRosterPlayer]:
    roster = fetch_team_roster(team_id, season=season, roster_type=roster_type)
    if not roster:
        raise HTTPException(status_code=404, detail=f"No live roster data was found for team {team_id}.")
    return [LiveRosterPlayer.model_validate(player) for player in roster]


@app.get("/live/schedule", response_model=list[LiveScheduleGame])
def get_live_schedule(
    team_id: str,
    start_date: str,
    end_date: str,
) -> list[LiveScheduleGame]:
    games = fetch_team_schedule(team_id, start_date=start_date, end_date=end_date)
    if not games:
        raise HTTPException(status_code=404, detail=f"No live schedule data was found for team {team_id}.")
    return [LiveScheduleGame.model_validate(game) for game in games]


@app.post("/matchups/draft", response_model=MatchupDraftResponse)
def draft_matchup(request: MatchupDraftRequest) -> MatchupDraftResponse:
    context, connection = require_database_connection()
    try:
        pitcher = fetch_pitcher_candidate(connection, request.pitcher_id)
        if pitcher is None:
            raise HTTPException(status_code=404, detail=f"Pitcher {request.pitcher_id} was not found.")

        opponent_team = fetch_team(connection, request.opponent_team_id)
        if opponent_team is None:
            raise HTTPException(status_code=404, detail=f"Team {request.opponent_team_id} was not found.")

        lineup = fetch_lineup_candidates(connection, team_id=request.opponent_team_id, limit=request.lineup_size)
        if not lineup:
            raise HTTPException(
                status_code=404,
                detail=f"No lineup candidates were found for team {request.opponent_team_id}.",
            )

        lineup_models = [
            LineupCandidate.model_validate(
                {
                    **candidate,
                    "plate_appearance_count": candidate["plate_appearance_count"],
                }
            )
            for candidate in lineup
        ]
        matchup_request = build_matchup_request_from_candidates(
            pitcher_id=pitcher["pitcher_id"],
            pitcher_name=pitcher["pitcher_name"],
            opponent_team_id=opponent_team["team_id"],
            lineup_models=lineup_models,
        )

        notes = [
            f"Draft lineup uses the top {len(lineup_models)} hitters by plate appearances for team {opponent_team['team_id']}.",
            "Pitcher identity currently comes from the loaded Statcast slice; some pitcher display names may need a richer identity source later.",
        ]

        return MatchupDraftResponse(
            pitcher=PitcherCandidate.model_validate(pitcher),
            opponent_team=TeamSummary.model_validate(opponent_team),
            lineup=lineup_models,
            matchup_request=matchup_request,
            notes=notes,
        )
    finally:
        context.__exit__(None, None, None)


@app.post("/matchups/smart-draft", response_model=SmartMatchupDraftResponse)
def smart_draft_matchup(request: SmartMatchupDraftRequest) -> SmartMatchupDraftResponse:
    context, connection = require_database_connection()
    try:
        schedule_games = fetch_team_schedule(
            request.team_id,
            start_date=request.game_date,
            end_date=request.game_date,
        )
        if not schedule_games:
            raise HTTPException(
                status_code=404,
                detail=f"No live schedule game was found for team {request.team_id} on {request.game_date}.",
            )

        selected_game = None
        if request.game_id is not None:
            for game in schedule_games:
                if game.get("game_id") == request.game_id:
                    selected_game = game
                    break
            if selected_game is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Game {request.game_id} was not found for team {request.team_id} on {request.game_date}.",
                )
        else:
            selected_game = schedule_games[0]

        team_id = request.team_id.lower()
        is_home = selected_game.get("home_team_id") == team_id
        opponent_team_id = selected_game.get("away_team_id") if is_home else selected_game.get("home_team_id")
        probable_pitcher_id = (
            selected_game.get("away_probable_pitcher_id")
            if is_home
            else selected_game.get("home_probable_pitcher_id")
        )
        probable_pitcher_name = (
            selected_game.get("away_probable_pitcher_name")
            if is_home
            else selected_game.get("home_probable_pitcher_name")
        )

        if not opponent_team_id:
            raise HTTPException(status_code=404, detail="Opponent team could not be determined from the selected game.")

        opponent_team = fetch_team(connection, opponent_team_id)
        if opponent_team is None:
            opponent_team = {
                "team_id": opponent_team_id,
                "name": selected_game.get("away_team_name") if is_home else selected_game.get("home_team_name") or opponent_team_id.upper(),
                "league": "MLB",
                "season": int(request.game_date[:4]),
            }

        lineup = fetch_lineup_candidates(connection, team_id=team_id, limit=request.lineup_size)
        if not lineup:
            raise HTTPException(
                status_code=404,
                detail=f"No lineup candidates were found for team {team_id}.",
            )

        lineup_models = [LineupCandidate.model_validate(candidate) for candidate in lineup]

        local_pitcher = None
        if isinstance(probable_pitcher_id, int):
            local_pitcher = fetch_player_by_mlbam_id(connection, probable_pitcher_id)

        pitcher_candidate = {
            "pitcher_id": local_pitcher["player_id"] if local_pitcher else f"pitcher_mlbam_{probable_pitcher_id}",
            "pitcher_name": local_pitcher["name"] if local_pitcher else (probable_pitcher_name or f"MLBAM {probable_pitcher_id}"),
            "throws": local_pitcher["throws"] if local_pitcher else None,
            "pitch_count": 0,
            "most_recent_game_date": selected_game.get("game_date"),
        }

        matchup_request = build_matchup_request_from_candidates(
            pitcher_id=pitcher_candidate["pitcher_id"],
            pitcher_name=pitcher_candidate["pitcher_name"],
            opponent_team_id=opponent_team["team_id"],
            lineup_models=lineup_models,
        )

        notes = [
            f"Selected live game {selected_game.get('game_id')} on {selected_game.get('game_date')} for team {team_id}.",
            f"Auto-built lineup from the top {len(lineup_models)} local lineup candidates for {team_id}.",
        ]
        if local_pitcher:
            notes.append("Mapped the live probable pitcher back into the local Statcast-backed player table.")
        else:
            notes.append("Live probable pitcher was not present in the local Statcast slice, so the draft uses an external MLBAM-backed pitcher ID.")

        return SmartMatchupDraftResponse(
            selected_game=LiveScheduleGame.model_validate(selected_game),
            opponent_team=TeamSummary.model_validate(opponent_team),
            pitcher=PitcherCandidate.model_validate(pitcher_candidate),
            lineup=lineup_models,
            matchup_request=matchup_request,
            notes=notes,
        )
    finally:
        context.__exit__(None, None, None)


@app.post("/matchups/compare", response_model=MatchupComparisonResponse)
def compare_matchups(request: MatchupComparisonRequest) -> MatchupComparisonResponse:
    context, connection = require_database_connection()
    try:
        saved_matchups = []
        for request_id in request.request_ids:
            saved_matchup = fetch_saved_matchup(connection, str(request_id))
            if saved_matchup is None:
                raise HTTPException(status_code=404, detail=f"Saved matchup {request_id} was not found.")
            saved_matchups.append(build_saved_matchup_summary(saved_matchup))

        baseline = saved_matchups[0]
        deltas = []
        for comparison in saved_matchups[1:]:
            baseline_overview = baseline.overview or MatchupOverview(
                expected_k_rate=0.0,
                expected_bb_rate=0.0,
                expected_bip_rate=0.0,
                expected_hard_hit_rate=0.0,
                estimated_run_value=0.0,
                summary="",
            )
            comparison_overview = comparison.overview or baseline_overview
            baseline_sim = baseline.simulation
            comparison_sim = comparison.simulation
            deltas.append(
                MatchupComparisonDelta(
                    baseline_request_id=baseline.request_id,
                    comparison_request_id=comparison.request_id,
                    expected_k_rate_delta=round(
                        comparison_overview.expected_k_rate - baseline_overview.expected_k_rate, 4
                    ),
                    expected_bb_rate_delta=round(
                        comparison_overview.expected_bb_rate - baseline_overview.expected_bb_rate, 4
                    ),
                    runs_scored_mean_delta=round(
                        ((comparison_sim.runs_scored.mean if comparison_sim else 0.0) - (baseline_sim.runs_scored.mean if baseline_sim else 0.0)),
                        4,
                    ),
                    home_runs_mean_delta=round(
                        ((comparison_sim.home_runs.mean if comparison_sim else 0.0) - (baseline_sim.home_runs.mean if baseline_sim else 0.0)),
                        4,
                    ),
                    run_value_mean_delta=round(
                        ((comparison_sim.run_value.mean if comparison_sim else 0.0) - (baseline_sim.run_value.mean if baseline_sim else 0.0)),
                        4,
                    ),
                )
            )

        return MatchupComparisonResponse(matchups=saved_matchups, deltas=deltas)
    finally:
        context.__exit__(None, None, None)


@app.get("/matchups/{request_id}", response_model=MatchupResponse)
def get_matchup(request_id: str) -> MatchupResponse:
    context, connection = require_database_connection()
    try:
        saved_matchup = fetch_saved_matchup(connection, request_id)
        if saved_matchup is None:
            raise HTTPException(status_code=404, detail=f"Saved matchup {request_id} was not found.")

        result_json = saved_matchup.get("result_json")
        if not isinstance(result_json, dict):
            raise HTTPException(status_code=404, detail=f"Saved matchup {request_id} has no persisted simulation payload.")

        return MatchupResponse(
            request_id=saved_matchup["request_id"],
            status=saved_matchup["status"],
            created_at=saved_matchup["created_at"],
            overview=MatchupOverview.model_validate(result_json["overview"]),
            hitter_projections=[
                HitterProjection.model_validate(item)
                for item in result_json.get("hitter_projections", [])
            ],
            simulation=SimulationSummary.model_validate(result_json["simulation"])
            if result_json.get("simulation")
            else None,
            next_step=result_json.get("next_step", "Persisted matchup retrieved from Postgres."),
        )
    finally:
        context.__exit__(None, None, None)


@app.post("/matchups", response_model=MatchupResponse, status_code=201)
def create_matchup(request: MatchupRequest) -> MatchupResponse:
    pitcher_name = request.pitcher_name or request.pitcher_id
    request_id = uuid4()
    artifacts = load_baseline_artifacts()

    with get_connection() as connection:
        latest_form = fetch_latest_pitcher_form(connection, request.pitcher_id) if connection else None
        pitcher_hand = fetch_pitcher_hand(connection, request.pitcher_id) if connection else None
        pitcher_hand = pitcher_hand if pitcher_hand in {"L", "R"} else "R"
        starter_split_key = f"vs_{pitcher_hand}"
        hitter_profiles = (
            fetch_hitter_profiles(
                connection,
                [hitter.hitter_id for hitter in request.lineup],
                split_key=starter_split_key,
            )
            if connection
            else {}
        )

        hitter_projections_raw = [
            score_hitter_projection(
                artifacts=artifacts,
                hitter=hitter.model_dump(),
                pitcher_hand=pitcher_hand,
                form_profile=latest_form,
                hitter_profile=hitter_profiles.get(hitter.hitter_id),
                manual_pitch_mix_adjustments=request.manual_pitch_mix_adjustments,
            )
            for hitter in request.lineup
        ]

        reliever_form = None
        reliever_hand = None
        reliever_hitter_projections = None
        if request.reliever_id:
            reliever_form = fetch_latest_pitcher_form(connection, request.reliever_id) if connection else None
            reliever_hand = fetch_pitcher_hand(connection, request.reliever_id) if connection else None
            reliever_hand = reliever_hand if reliever_hand in {"L", "R"} else "R"
            reliever_split_key = f"vs_{reliever_hand}"
            reliever_hitter_profiles = (
                fetch_hitter_profiles(
                    connection,
                    [hitter.hitter_id for hitter in request.lineup],
                    split_key=reliever_split_key,
                )
                if connection
                else {}
            )
            reliever_hitter_projections = [
                score_hitter_projection(
                    artifacts=artifacts,
                    hitter=hitter.model_dump(),
                    pitcher_hand=reliever_hand,
                    form_profile=reliever_form,
                    hitter_profile=reliever_hitter_profiles.get(hitter.hitter_id),
                    manual_pitch_mix_adjustments={},
                )
                for hitter in request.lineup
            ]

        simulation_result = run_matchup_simulation(
            hitter_projections=hitter_projections_raw,
            iteration_count=500,
            seed=request_id.int % (2**32),
            reliever_hitter_projections=reliever_hitter_projections,
            reliever_entry_batter_number=request.reliever_entry_batter_number,
            reliever_entry_inning=request.reliever_entry_inning,
        )

        strikeout_rate = average_projection_metric(hitter_projections_raw, "estimated_k_rate", 0.24)
        walk_rate = average_projection_metric(hitter_projections_raw, "estimated_bb_rate", 0.08)
        bip_rate = average_projection_metric(hitter_projections_raw, "estimated_bip_rate", 0.68)
        hard_hit_rate = average_projection_metric(hitter_projections_raw, "hard_hit_rate_on_contact", 0.34)
        estimated_run_value = average_projection_metric(hitter_projections_raw, "estimated_run_value", 0.12)

        summary_parts = []
        if artifacts:
            summary_parts.append("Using saved baseline swing and contact model artifacts for matchup scoring.")
        else:
            summary_parts.append("Model artifacts were not found, so scoring fell back to profile-informed priors.")
        if latest_form:
            summary_parts.append(
                f"Using pitcher form window ending {latest_form['window_end']} with {latest_form['sample_pitch_count']} tracked pitches."
            )
        else:
            summary_parts.append("No stored pitcher form window was found, so pitcher context used fallback assumptions.")
        if hitter_profiles:
            summary_parts.append(
                f"Matched {len(hitter_profiles)} lineup hitters to stored {starter_split_key} tendency profiles."
            )
        else:
            summary_parts.append(f"No hitter tendency profiles were found for split {starter_split_key}.")
        summary_parts.append("Simulation now applies times-through-the-order adjustments across the starter outing.")
        if request.reliever_id:
            reliever_name = request.reliever_name or request.reliever_id
            entry_batter_number = request.reliever_entry_batter_number or 19
            summary_parts.append(
                f"Reliever transition enabled for {reliever_name} starting around batter {entry_batter_number}."
            )
            if request.reliever_entry_inning is not None:
                summary_parts.append(
                    f"Inning-aware handoff enabled beginning in inning {request.reliever_entry_inning}, with inherited runners tracked through the transition."
                )
            if reliever_form:
                summary_parts.append(
                    f"Using reliever form window ending {reliever_form['window_end']} for the late-game handoff."
                )
            else:
                summary_parts.append("No stored reliever form window was found, so the handoff used fallback reliever assumptions.")

        overview = MatchupOverview(
            expected_k_rate=strikeout_rate,
            expected_bb_rate=walk_rate,
            expected_bip_rate=bip_rate,
            expected_hard_hit_rate=hard_hit_rate,
            estimated_run_value=estimated_run_value,
            summary=" ".join(summary_parts),
        )

        status = "simulated" if connection else "simulated_without_persistence"

        if connection:
            persisted_result = {
                "overview": overview.model_dump(),
                "hitter_projections": hitter_projections_raw,
                "simulation": simulation_result,
                "next_step": (
                    "Calibrate the baseline artifacts against held-out samples, then replace these heuristics with "
                    "trained pitch-level and plate-appearance probability models."
                ),
            }
            insert_matchup_request(
                connection=connection,
                request_id=str(request_id),
                pitcher_id=request.pitcher_id,
                opponent_team_id=request.opponent_team_id,
                lineup_json=[hitter.model_dump() for hitter in request.lineup],
                form_window_id=str(latest_form["form_window_id"]) if latest_form else None,
                status=status,
            )
            simulation_id = uuid5(NAMESPACE_URL, f"simulation:{request_id}")
            insert_simulation_run(
                connection=connection,
                simulation_id=str(simulation_id),
                request_id=str(request_id),
                model_version="baseline_v1",
                iteration_count=simulation_result["iteration_count"],
                result_json=persisted_result,
            )
            connection.commit()

    return MatchupResponse(
        request_id=request_id,
        status=status,
        created_at=datetime.now(UTC),
        overview=overview,
        hitter_projections=[HitterProjection.model_validate(item) for item in hitter_projections_raw],
        simulation=SimulationSummary.model_validate(simulation_result),
        next_step=(
            "Calibrate the baseline artifacts against held-out samples, then replace these heuristics with "
            "trained pitch-level and plate-appearance probability models."
        ),
    )


@app.post("/matchups/prepare", response_model=PrepareMatchupResponse)
def prepare_matchup(request: PrepareMatchupRequest) -> PrepareMatchupResponse:
    draft = smart_draft_matchup(
        SmartMatchupDraftRequest(
            team_id=request.team_id,
            game_date=request.game_date,
            game_id=request.game_id,
            lineup_size=request.lineup_size,
        )
    )

    if request.lineup_override:
        draft = apply_lineup_override_to_draft(draft, [hitter.model_dump() for hitter in request.lineup_override])

    matchup_request = MatchupRequest.model_validate(
        {
            **draft.matchup_request.model_dump(),
            "reliever_id": request.reliever_id,
            "reliever_name": request.reliever_name,
            "reliever_entry_batter_number": request.reliever_entry_batter_number,
            "reliever_entry_inning": request.reliever_entry_inning,
            "manual_pitch_mix_adjustments": request.manual_pitch_mix_adjustments,
        }
    )
    matchup_response = create_matchup(matchup_request)

    notes = list(draft.notes)
    if request.manual_pitch_mix_adjustments:
        notes.append("Applied manual pitch-mix overrides before running the matchup.")
    else:
        notes.append("Ran the matchup directly from the smart draft without pitch-mix overrides.")
    if request.reliever_id:
        reliever_name = request.reliever_name or request.reliever_id
        entry_batter = request.reliever_entry_batter_number or 19
        notes.append(f"Late-game reliever handoff enabled for {reliever_name} around batter {entry_batter}.")
        if request.reliever_entry_inning is not None:
            notes.append(
                f"Reliever entry is also eligible starting in inning {request.reliever_entry_inning}, and inherited runners stay attached to the starter."
            )

    return PrepareMatchupResponse(draft=draft, matchup=matchup_response, notes=notes)


def score_and_simulate_lineup(
    connection: object,
    artifacts: object,
    matchup_request: MatchupRequest,
    seed: int,
    iteration_count: int,
) -> dict[str, object]:
    latest_form = fetch_latest_pitcher_form(connection, matchup_request.pitcher_id) if connection else None
    pitcher_hand = fetch_pitcher_hand(connection, matchup_request.pitcher_id) if connection else None
    pitcher_hand = pitcher_hand if pitcher_hand in {"L", "R"} else "R"
    split_key = f"vs_{pitcher_hand}"
    hitter_profiles = (
        fetch_hitter_profiles(
            connection,
            [hitter.hitter_id for hitter in matchup_request.lineup],
            split_key=split_key,
        )
        if connection
        else {}
    )

    hitter_projections = [
        score_hitter_projection(
            artifacts=artifacts,
            hitter=hitter.model_dump(),
            pitcher_hand=pitcher_hand,
            form_profile=latest_form,
            hitter_profile=hitter_profiles.get(hitter.hitter_id),
            manual_pitch_mix_adjustments=matchup_request.manual_pitch_mix_adjustments,
        )
        for hitter in matchup_request.lineup
    ]

    return run_matchup_simulation(
        hitter_projections=hitter_projections,
        iteration_count=iteration_count,
        seed=seed,
        collect_samples=True,
    )


@app.post("/trades/evaluate", response_model=TradeEvaluationResponse)
def evaluate_trade(request: TradeEvaluationRequest) -> TradeEvaluationResponse:
    schedule_games = fetch_team_schedule(
        request.team_id,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    if not schedule_games:
        raise HTTPException(
            status_code=404,
            detail=f"No live schedule games were found for team {request.team_id} between {request.start_date} and {request.end_date}.",
        )
    selected_games = schedule_games[: request.max_games]

    artifacts = load_baseline_artifacts()
    context, connection = require_database_connection()
    try:
        game_deltas: list[TradeGameDelta] = []
        runs_delta_samples_by_game: list[list[float]] = []
        run_value_delta_samples_by_game: list[list[float]] = []
        displaced_hitter: TradeHitter | None = None

        for game in selected_games:
            draft = smart_draft_matchup(
                SmartMatchupDraftRequest(
                    team_id=request.team_id,
                    game_date=str(game.get("game_date")),
                    game_id=game.get("game_id"),
                    lineup_size=request.lineup_size,
                )
            )

            baseline_lineup = [hitter.model_dump() for hitter in draft.matchup_request.lineup]
            try:
                variant_lineup = build_variant_lineup(
                    lineup=baseline_lineup,
                    displaced_hitter_id=request.displaced_hitter_id,
                    incoming_hitter=request.incoming_hitter.model_dump(),
                )
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error

            if displaced_hitter is None:
                displaced = next(
                    hitter for hitter in baseline_lineup if hitter["hitter_id"] == request.displaced_hitter_id
                )
                displaced_hitter = TradeHitter(
                    hitter_id=displaced["hitter_id"],
                    hitter_name=displaced["hitter_name"],
                    batting_side=displaced.get("batting_side"),
                )

            variant_draft = apply_lineup_override_to_draft(draft, variant_lineup)

            seed = uuid5(NAMESPACE_URL, f"trade:{request.team_id}:{game.get('game_id')}").int % (2**32)
            baseline_simulation = score_and_simulate_lineup(
                connection=connection,
                artifacts=artifacts,
                matchup_request=draft.matchup_request,
                seed=seed,
                iteration_count=request.iteration_count,
            )
            variant_simulation = score_and_simulate_lineup(
                connection=connection,
                artifacts=artifacts,
                matchup_request=variant_draft.matchup_request,
                seed=seed,
                iteration_count=request.iteration_count,
            )

            runs_deltas = paired_delta_samples(
                baseline_simulation["samples"]["runs_scored"],
                variant_simulation["samples"]["runs_scored"],
            )
            run_value_deltas = paired_delta_samples(
                baseline_simulation["samples"]["run_value"],
                variant_simulation["samples"]["run_value"],
            )
            runs_delta_samples_by_game.append(runs_deltas)
            run_value_delta_samples_by_game.append(run_value_deltas)

            game_deltas.append(
                TradeGameDelta(
                    game_id=game.get("game_id"),
                    game_date=game.get("game_date"),
                    opponent_team_id=draft.opponent_team.team_id,
                    opposing_pitcher_name=draft.pitcher.pitcher_name,
                    baseline_runs_mean=baseline_simulation["runs_scored"]["mean"],
                    variant_runs_mean=variant_simulation["runs_scored"]["mean"],
                    runs_delta=TradeDeltaSummary.model_validate(summarize_delta(runs_deltas)),
                    run_value_delta=TradeDeltaSummary.model_validate(summarize_delta(run_value_deltas)),
                )
            )

        window_runs_delta = aggregate_window_deltas(runs_delta_samples_by_game)
        window_run_value_delta = aggregate_window_deltas(run_value_delta_samples_by_game)

        notes = [
            f"Evaluated {len(game_deltas)} upcoming games for {request.team_id} between {request.start_date} and {request.end_date}.",
            f"Swapped {request.incoming_hitter.hitter_name} in for {displaced_hitter.hitter_name} at the same lineup spot in every game.",
            "Baseline and variant lineups were simulated with common random numbers per game, so paired deltas isolate the player swap.",
            "The p10-p90 band shows single-game outcome variability; the mean confidence interval says whether the swap's average effect is distinguishable from zero.",
            "Window totals sum paired per-iteration deltas across games, giving a full distribution for runs added over the evaluation window.",
        ]

        return TradeEvaluationResponse(
            team_id=request.team_id,
            incoming_hitter=request.incoming_hitter,
            displaced_hitter=displaced_hitter,
            games_evaluated=len(game_deltas),
            iteration_count=request.iteration_count,
            game_deltas=game_deltas,
            window_runs_delta=TradeDeltaSummary.model_validate(window_runs_delta),
            window_run_value_delta=TradeDeltaSummary.model_validate(window_run_value_delta),
            runs_delta_per_game=round(window_runs_delta["mean"] / len(game_deltas), 4),
            notes=notes,
        )
    finally:
        context.__exit__(None, None, None)
