# Baseball Simulator

Initial implementation scaffold for the public-data-first baseball matchup simulator.

## What Exists

- `infrastructure/sql/001_init.sql`: starter Postgres schema and indexes
- `services/etl/statcast_pull.py`: pull or copy a narrow Statcast CSV extract
- `services/etl/build_features.py`: derive normalized dimension and fact JSONL files
- `services/etl/build_profiles.py`: derive pitcher form-window and hitter tendency profiles
- `services/etl/load_to_postgres.py`: upsert processed JSONL artifacts into Postgres
- `infrastructure/scripts/apply_schema.py`: apply the starter Postgres schema
- `infrastructure/scripts/bootstrap_pipeline.py`: run pull/build/load steps end to end
- `services/modeling/train_swing_model.py`: train a lightweight swing-rate baseline artifact
- `services/modeling/train_contact_model.py`: train a lightweight contact baseline artifact
- `services/modeling/train_pa_outcome_model.py`: train a direct plate-appearance outcome artifact for `BB/K/1B/2B/3B/HR/BIP out`
- `infrastructure/scripts/evaluate_model_windows.py`: train baseline artifacts across one or more processed windows and write a combined calibration report
- `infrastructure/scripts/evaluate_pooled_pa_model.py`: train one pooled PA outcome artifact and validate it across multiple windows
- `infrastructure/scripts/train_default_pooled_pa_model.py`: write the API's default PA outcome artifact from pooled processed windows
- `services/modeling/baseline_utils.py`: shared training, holdout-split, and calibration helpers for baseline artifacts
- `services/modeling/inference.py`: load saved artifacts and score hitter-level matchup projections
- `services/simulation/engine.py`: run the first Monte Carlo matchup simulation summary
- `services/trades/evaluator.py`: paired-delta comparison math for the trade evaluator (common random numbers, mean confidence intervals)
- `apps/api/main.py`: FastAPI app with `GET /health`, `POST /matchups`, and `POST /trades/evaluate`
- `packages/shared_types/matchups.py`: shared request and response schemas

## Quick Start

Install dependencies:

```bash
uv sync
```

The API and Postgres loader depend on installed project packages, so `uv sync` is required before running them.

Run the API:

```bash
uv run uvicorn apps.api.main:app --reload
```

The same FastAPI process now serves the web interface at:

```bash
http://127.0.0.1:8000/
```

Pull a raw Statcast extract:

```bash
uv run python services/etl/statcast_pull.py --start-date 2025-06-01 --end-date 2025-06-07
```

Build normalized feature files:

```bash
uv run python services/etl/build_features.py --input data/raw/statcast_2025-06-01_2025-06-07.csv
```

Build pitcher and hitter profile aggregates:

```bash
uv run python services/etl/build_profiles.py --input-dir data/processed --output-dir data/processed --window-days 30
```

Apply the schema to Postgres:

```bash
uv run python infrastructure/scripts/apply_schema.py --database-url postgresql://user:pass@localhost:5432/baseball_sim
```

Load processed artifacts into Postgres:

```bash
uv run python services/etl/load_to_postgres.py --database-url postgresql://user:pass@localhost:5432/baseball_sim --input-dir data/processed
```

Run the API against Postgres:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/baseball_sim uv run uvicorn apps.api.main:app --reload
```

Start local Postgres with OrbStack's Docker context:

```bash
docker --context orbstack compose -f infrastructure/docker/postgres-compose.yml up -d
```

The local database created by that Compose file uses:

- host: `localhost`
- port: `5432`
- database: `baseball_sim`
- user: `baseball`
- password: `baseball_dev`

Application connection string:

```bash
export DATABASE_URL=postgresql://baseball:baseball_dev@localhost:5432/baseball_sim
```

Apply the schema after Postgres is healthy:

```bash
uv run python infrastructure/scripts/apply_schema.py --database-url "$DATABASE_URL"
```

Stop the local database:

```bash
docker --context orbstack compose -f infrastructure/docker/postgres-compose.yml down
```

The `POST /matchups` endpoint now returns:

- matchup overview rates
- hitter-level projections
- a first simulation summary

`POST /matchups` also now supports an optional reliever handoff through `reliever_id`, `reliever_name`, `reliever_entry_batter_number`, and `reliever_entry_inning`, and the simulation applies times-through-the-order adjustments to the starter by default while tracking inherited runners across the bullpen transition.

When `DATABASE_URL` is configured, it also persists `matchup_requests` and `simulation_runs`.

Persisted matchup endpoints:

- `GET /matchups`: list recent saved matchup runs
- `GET /matchups/{request_id}`: retrieve one saved matchup payload
- `POST /matchups/compare`: compare saved matchup runs by request ID
- `GET /teams`: list teams available in the loaded season slice
- `GET /teams/{team_id}/lineup-candidates`: list likely hitters for matchup setup
- `GET /teams/{team_id}/bullpen-candidates`: list likely reliever candidates from the loaded slice
- `GET /pitchers`: list pitcher candidates available in the loaded slice
- `POST /matchups/draft`: build a matchup-ready request from a pitcher and opponent team
- `GET /live/teams/{team_id}/roster`: fetch live team roster context from the MLB Stats API
- `GET /live/schedule`: fetch live team schedule and probable-pitcher context from the MLB Stats API
- `POST /matchups/smart-draft`: build a matchup-ready request from a live scheduled game plus local lineup candidates
- `POST /matchups/prepare`: smart-draft a matchup, apply optional pitch-mix overrides, run it, and persist the result

Web interface capabilities:

- choose a team and date
- preview the smart draft
- adjust pitch mix
- optionally select a reliever handoff, batter trigger, and inning trigger
- review inherited-runner impact from the bullpen transition
- run and persist the prepared matchup
- compare two saved scenarios side by side from the recent-runs panel
- inspect simulation output
- review recent saved runs

Player identity enrichment:

- `uv run python services/etl/enrich_players.py --input data/processed/players.jsonl`

This uses the MLB Stats API people endpoint to repair player names and handedness, which is especially important for pitcher identity because the raw Statcast CSV does not include a clean pitcher-name column.

Run the end-to-end bootstrap command:

```bash
uv run python infrastructure/scripts/bootstrap_pipeline.py --start-date 2025-06-01 --end-date 2025-06-07 --database-url postgresql://user:pass@localhost:5432/baseball_sim --apply-schema
```

Train the first baseline model artifacts:

```bash
uv run python services/modeling/train_swing_model.py --input-dir data/processed
uv run python services/modeling/train_contact_model.py --input-dir data/processed
uv run python services/modeling/train_pa_outcome_model.py --input-dir data/processed
```

Those training commands now reserve the most recent game slice as a holdout set, write calibration summaries into the artifacts, and apply those holdout-derived correction factors during API inference. The PA outcome model also gives the simulator a learned path for direct `walk`, `strikeout`, hit-type, and `ball_in_play_out` probabilities.

Compare calibration across one or more processed windows:

```bash
uv run python infrastructure/scripts/evaluate_model_windows.py --window june_01_04=data/processed
```

Repeat `--window` to compare multiple processed directories. The script writes:

- `artifacts/models/eval_windows/<label>/...` for per-window trained artifacts
- `artifacts/reports/model_window_evaluation.json` for machine-readable metrics
- `artifacts/reports/model_window_evaluation.md` for a quick human-readable summary

Train a pooled PA outcome artifact and validate it across windows:

```bash
uv run python infrastructure/scripts/evaluate_pooled_pa_model.py \
  --train-window may_24_27=data/processed/windows/may_24_27 \
  --train-window june_01_04=data/processed \
  --eval-window may_24_27=data/processed/windows/may_24_27 \
  --eval-window june_01_04=data/processed \
  --eval-window june_08_11=data/processed/windows/june_08_11
```

Promote the pooled PA model into the API's default artifact path:

```bash
uv run python infrastructure/scripts/train_default_pooled_pa_model.py \
  --window may_24_27=data/processed/windows/may_24_27 \
  --window june_01_04=data/processed \
  --window june_08_11=data/processed/windows/june_08_11
```

Run the API and simulation tests:

```bash
uv run pytest tests/test_matchups_api.py tests/test_simulation_engine.py tests/test_enrich_players.py tests/test_inference.py tests/test_build_features.py
```

## Next Recommended Steps

1. Improve the new PA outcome model with richer per-PA features such as count state, pitcher recent-form buckets, and matchup-specific damage context.
2. Add richer simulation state so times-through-order, reliever transitions, and run environments are modeled more realistically.
3. Add more request-level and browser-level verification for the matchup-prep workflow.
