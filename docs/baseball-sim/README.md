# Baseball Matchup Simulator

This document set is the starter blueprint for a baseball analytics application that:

- ingests public pitch-level and hitter tendency data
- estimates how a pitcher's current pitch profile should perform against a specific lineup
- simulates matchup outcomes with uncertainty bands
- leaves room for future bullpen TrackMan uploads

The first version should be built with public MLB data so the modeling and product workflow can be validated before integrating licensed or proprietary sources.

## Document Map

- `product-spec.md`: v1 scope, users, inputs, outputs, and success criteria
- `database-schema.md`: starter relational schema for the app and modeling pipeline
- `feature-catalog.md`: initial feature set for baseline models
- `repo-structure.md`: suggested project layout and service boundaries
- `handoff.md`: current build status and where the project is headed next

## V1 Product Summary

The v1 application should answer:

"Given a pitcher's recent pitch profile and a target lineup, what are the expected strikeout, walk, contact quality, and run prevention outcomes, and what pitch usage plan looks best?"

## Key Constraints

- No private TrackMan dependency in v1
- Public-data-first pipeline using Statcast, FanGraphs-style aggregates, and optional Retrosheet history
- Focus on probabilistic projections, not deterministic claims
- Keep pitcher "current form" support modular so bullpen session data can be attached later
