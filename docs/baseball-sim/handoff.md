# Handoff — 2026-07-17

Working notes for picking this project back up on another machine or in a fresh session.

## Where Things Stand

The core matchup pipeline is built and working: Statcast-backed lineup candidates, baseline
swing/contact/PA-outcome models (`services/modeling/`), a Monte Carlo matchup engine
(`services/simulation/engine.py`), a FastAPI app (`apps/api/main.py`), and a working web UI
(`apps/web/`) that drafts a matchup, tunes the pitch mix, runs the simulation, and saves/compares
runs.

Latest addition: a **trade evaluator** (`POST /trades/evaluate`, `services/trades/evaluator.py`,
plus a "Trade Evaluator" section in the web UI). Given a team, an incoming hitter, and the hitter
they'd displace, it re-simulates the team's next N scheduled games with and without the swap,
using the *same random seed* for both runs per game (common random numbers) so the resulting
run delta isolates the player swap rather than Monte Carlo noise. It reports two different bands
on purpose:

- **p10/p50/p90** — single-game outcome variability (this will be wide; that's real baseball
  variance, not a bug).
- **90% CI on the mean delta** (`mean_ci_low` / `mean_ci_high`) — whether the swap's *average*
  effect is distinguishable from zero. This is the number that answers "is this a real trade
  upgrade" rather than "how much could any given game vary."

All 43 tests pass (`uv run pytest`). Verified live in the browser: swapped Aaron Judge in for
Nolan Schanuel in the Angels' projected lineup and confirmed the UI renders per-game deltas, the
window total, and the confidence band correctly.

## Known Limitation Worth Fixing Next

Incoming trade targets who aren't in the local Statcast hitter-tendency profile table fall back
toward league-average priors when scored against the opposing pitcher's split. This mutes how
much a real star upgrade should move the projection — it's why a Judge-for-Schanuel swap in
testing showed a small, noise-dominated delta instead of a clearly positive one. Backfilling
tendency profiles for realistic trade targets (not just current roster players) is the highest-
leverage next step before trusting the evaluator's numbers for actual trade reads.

## How To Run Locally

```bash
# Postgres runs in Docker as `baseball-sim-postgres`
DATABASE_URL=postgresql://baseball:baseball_dev@localhost:5432/baseball_sim \
  uv run uvicorn apps.api.main:app --reload
```

Open `http://localhost:8000`. The local Statcast slice is 2025 season data, so the UI's default
game date (2025-06-03) is a safe starting point for the matchup builder; the trade evaluator's
date window should also fall within data you actually have loaded.

Run tests with `uv run pytest`.

## Where This Is Headed

This project is the active build for a broader "baseball analytics playground" — the trade
evaluator is the first of several planned layers on top of the existing simulation core:

- **Player projections** — season-level rollups on top of the existing PA-outcome model.
- **"What if the rules were different" sims** — re-run the engine with modified transition
  probabilities (e.g., no shift, different DH rules); the Monte Carlo engine already supports
  swapping in adjusted projections, which is most of what this needs.
- **Betting angles** — `infrastructure/scripts/evaluate_model_windows.py` already writes
  calibration reports for the baseline models; the natural next step is comparing simulated
  win/run-total probabilities against actual sportsbook lines to see if the model has edge.

None of these are started yet. The trade evaluator is a template for the pattern: pure comparison
math in its own `services/<feature>/` module, a thin FastAPI endpoint that composes existing
drafting/scoring/simulation machinery, and a UI section that reuses the existing panel layout.
