# Feature Catalog

## Goal

The first model stack should predict:

- swing versus take
- whiff or contact on swings
- quality of contact when the ball is put in play
- plate appearance level outcomes such as strikeout, walk, and run contribution

## Modeling Philosophy

Start with interpretable and maintainable tabular features. Only add complexity after baseline calibration and feature importance are understood.

## Feature Groups

### 1. Pitcher Identity And Baseline

- pitcher handedness
- starter versus reliever role
- season-level pitch usage mix
- recent form window pitch usage mix
- recent form window average velocity by pitch type
- recent form window average movement by pitch type
- recent form window command stability metrics

### 2. Pitch-Level Characteristics

- pitch type
- release speed
- spin rate
- extension
- horizontal break
- induced vertical break proxy or vertical movement
- release side and release height
- pitch location at plate
- zone bucket
- edge versus heart location bucket

### 3. Count And Sequence Context

- balls
- strikes
- full count flag
- two-strike flag
- first-pitch flag
- previous pitch type
- previous pitch location bucket
- previous pitch result
- pitch-type repeat flag

### 4. Hitter Identity And Tendencies

- hitter handedness
- hitter swing rate overall
- hitter chase rate
- hitter zone swing rate
- hitter whiff rate by pitch type
- hitter hard-hit or damage by pitch type
- hitter slugging or expected damage by zone bucket
- hitter split versus pitcher handedness

### 5. Matchup Interaction Features

- pitcher hand x hitter side
- pitch type x hitter side
- pitch type x hitter whiff tendency
- zone bucket x hitter chase tendency
- zone bucket x hitter damage tendency
- velocity differential versus hitter weakness band

### 6. Aggregated Pitcher "Current Form" Features

These become especially important once bullpen uploads exist.

- deviation from season baseline velocity by pitch type
- deviation from season baseline movement by pitch type
- recent usage increase or decrease by pitch type
- command spread by intended region
- release consistency metrics

### 7. Team Or Lineup Features

- projected lineup order
- number of left-handed hitters
- number of hitters with plus damage against a specific pitch type
- lineup aggregate chase tendency
- lineup aggregate in-zone damage tendency

## First Labels To Train

### Pitch-Level Labels

- `swing_flag`
- `whiff_flag`
- `called_strike_flag`
- `in_play_flag`
- `hard_hit_flag`

### Plate Appearance Labels

- `strikeout_flag`
- `walk_flag`
- `hit_by_pitch_flag`
- `extra_base_hit_flag`
- `pa_run_value`

## Recommended First Models

### Model 1: Swing Decision

Predict whether the hitter offers at the pitch.

Likely target:

- binary classification

### Model 2: Swing Outcome

Conditional on a swing, predict:

- whiff
- foul
- ball in play

Likely target:

- multiclass classification

### Model 3: Contact Quality

Conditional on ball in play, predict:

- weak contact
- medium contact
- hard-hit or expected damage bucket

Likely target:

- classification or regression depending on label choice

### Model 4: Plate Appearance Outcome

Estimate the overall PA-level result from sequential pitch expectations or directly from summarized matchup features.

Likely target:

- multinomial classification or calibrated binary submodels

## Evaluation Priorities

- calibration before raw accuracy
- split evaluation by handedness
- hold out by time to reduce leakage
- inspect feature stability over multiple date windows

## Features To Delay Until Later

- weather
- umpire tendencies
- catcher framing
- defense quality
- park-adjusted carry effects
- fatigue and recovery models

These can improve realism later, but they should not block the first usable prototype.
