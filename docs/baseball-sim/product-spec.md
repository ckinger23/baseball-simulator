# Product Spec

## Product Name

Baseball Matchup Simulator

## Problem

Coaches, analysts, and player development staff need a faster way to estimate how a pitcher should perform against a specific team or lineup based on pitch characteristics, hitter tendencies, and likely pitch usage. Existing workflows often require switching between multiple scouting tools, manual heat map review, and subjective synthesis.

## Vision

Turn pitcher pitch traits plus hitter zone and pitch-type tendencies into a matchup report and simulation engine that helps users:

- project likely pitcher outcomes against a lineup
- identify which hitters and zones are most dangerous
- recommend pitch usage adjustments
- compare multiple lineup or pitch-mix scenarios

## Target Users

- professional baseball analysts
- college baseball player development staff
- pitching coaches
- advance scouts

## V1 Users

The initial build should optimize for a baseball-savvy analyst user who is comfortable reading pitch metrics, heat maps, and probabilistic outputs.

## V1 Inputs

- pitcher identity
- target team or lineup
- date range for pitcher form window
- pitch-level public tracking data
- hitter tendency data by zone and pitch type
- optional manual pitch-mix adjustment inputs

## V1 Outputs

- expected `K%`, `BB%`, `BIP%`, `hard-hit%`, and estimated run value
- hitter-by-hitter matchup summary
- zone heat maps for hitter damage and pitcher success
- pitch usage recommendation by hitter handedness and lineup spot
- simulation distribution for core outcomes across many runs

## Non-Goals For V1

- full game strategy engine with bullpen management
- biomechanical injury prediction
- catcher framing and defensive alignment modeling
- NCAA or pro proprietary-data ingestion
- live in-game decision support

## Public Data Assumption

V1 is built around MLB public data that approximates the eventual private-data workflow:

- Statcast pitch-level characteristics and outcomes
- team and hitter discipline tendencies
- historical outcome records

This allows the architecture to be validated before real bullpen session files are introduced.

## Primary User Workflow

1. User selects a pitcher and target lineup.
2. System builds a pitcher profile from a recent date window.
3. System builds hitter tendency profiles for the opposing lineup.
4. Model estimates pitch and plate appearance outcome probabilities.
5. Simulator runs many matchup trials.
6. UI returns a report with expected outcomes, heat maps, and recommended pitch usage.

## Core Product Questions

- How does this pitcher profile project against this lineup?
- Which hitters profile as strongest or weakest matchups?
- Where should the pitcher avoid or attack in the zone?
- Which pitch types are likely over- or under-used?
- How volatile is the projection?

## MVP Screens

- pitcher search and matchup setup
- lineup selection and handedness view
- matchup overview dashboard
- hitter detail page with zone and pitch-type breakdown
- simulation summary with percentile outcomes

## Success Metrics

- users can generate a matchup report in under 30 seconds after data is prepared
- projected K and BB rates are directionally useful versus held-out samples
- users can explain recommended pitch-mix changes from the UI without exporting data elsewhere
- calibration error remains acceptable for core projected outcomes

## Risks

- public data is not a perfect substitute for bullpen TrackMan
- pitcher form windows may be noisy with small samples
- team-level views can overstate confidence if projected lineups change
- zone and pitch-type interactions can become sparse quickly

## Future Extensions

- bullpen TrackMan upload and today's readiness adjustments
- D1 data adapters where access exists
- custom player reports and PDF export
- scenario comparison across multiple lineups
- analyst notes and manual overrides
