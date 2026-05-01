# Repo Structure

## Goal

Keep the system simple enough for one developer to build while leaving clear seams for data ingestion, modeling, API delivery, and frontend reporting.

## Suggested Top-Level Layout

```text
baseball-matchup-sim/
  apps/
    api/
    web/
  packages/
    data-models/
    shared-types/
    ui/
  services/
    etl/
    modeling/
    simulation/
  infrastructure/
    sql/
    scripts/
  docs/
```

## Suggested Responsibilities

### `apps/api`

FastAPI service that:

- exposes matchup creation endpoints
- serves pitcher, hitter, team, and simulation result data
- triggers model inference or reads precomputed outputs

### `apps/web`

Frontend application that:

- lets a user select pitcher, lineup, and form window
- renders heat maps and matchup summaries
- displays simulation distributions and recommendations

### `packages/data-models`

Shared data contracts and schema helpers:

- ORM models or SQLModel definitions
- pydantic schemas
- transformation helpers for domain entities

### `packages/shared-types`

Cross-service types for:

- matchup requests
- simulation responses
- chart payloads
- pitch profile summaries

### `packages/ui`

Reusable chart and report components:

- zone heat map
- pitch usage chart
- matchup summary cards
- simulation percentile views

### `services/etl`

Data ingestion and preparation:

- pull Statcast and public baseball data
- normalize raw files
- create derived modeling tables
- materialize pitcher and hitter profiles

### `services/modeling`

Training and inference logic:

- feature builders
- model training scripts
- model registry metadata
- offline evaluation reports

### `services/simulation`

Simulation engine:

- pitch or PA state transitions
- Monte Carlo logic
- aggregation to report-friendly summaries

### `infrastructure/sql`

- base table DDL
- materialized view definitions
- indexes
- migration helpers

### `infrastructure/scripts`

- local setup helpers
- data backfill commands
- scheduled refresh commands

## Suggested V1 Milestones By Folder

### Milestone 1

- create `services/etl` pipeline for a narrow Statcast date range
- create `infrastructure/sql` schema files
- stand up `apps/api` with health and matchup stub endpoints

### Milestone 2

- build first feature tables in `services/modeling`
- train baseline models
- return mock matchup reports from `apps/api`

### Milestone 3

- build `apps/web` setup screen and matchup dashboard
- integrate first simulation summaries
- add heat maps and hitter detail views

### Milestone 4

- add `bullpen_sessions` ingestion contract
- compare uploaded session traits against historical profile
- introduce form-based adjustment logic

## Suggested First Real Files

```text
docs/
  baseball-sim/
    README.md
    product-spec.md
    database-schema.md
    feature-catalog.md
    repo-structure.md
```

After these docs, the next implementation pass should create:

```text
services/etl/statcast_pull.py
services/etl/build_features.py
services/modeling/train_swing_model.py
services/modeling/train_contact_model.py
apps/api/main.py
infrastructure/sql/001_init.sql
```
