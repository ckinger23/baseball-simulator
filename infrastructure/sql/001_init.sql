CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    mlbam_id BIGINT,
    name TEXT NOT NULL,
    bats TEXT,
    throws TEXT,
    primary_role TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT NOT NULL,
    league TEXT NOT NULL,
    name TEXT NOT NULL,
    season INT NOT NULL,
    PRIMARY KEY (team_id, season)
);

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    game_date DATE NOT NULL,
    season INT NOT NULL,
    home_team_id TEXT NOT NULL,
    away_team_id TEXT NOT NULL,
    venue TEXT
);

CREATE TABLE IF NOT EXISTS plate_appearances (
    pa_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES games (game_id),
    inning INT,
    top_bottom TEXT,
    pitcher_id TEXT NOT NULL REFERENCES players (player_id),
    hitter_id TEXT NOT NULL REFERENCES players (player_id),
    batting_team_id TEXT NOT NULL,
    fielding_team_id TEXT NOT NULL,
    outs_start INT,
    base_state_start TEXT,
    result TEXT,
    runs_scored INT,
    woba_value NUMERIC,
    run_value NUMERIC
);

CREATE TABLE IF NOT EXISTS pitches (
    pitch_id TEXT PRIMARY KEY,
    pa_id TEXT NOT NULL REFERENCES plate_appearances (pa_id),
    game_id TEXT NOT NULL REFERENCES games (game_id),
    pitch_number INT,
    pitcher_id TEXT NOT NULL REFERENCES players (player_id),
    hitter_id TEXT NOT NULL REFERENCES players (player_id),
    pitch_type TEXT,
    pitcher_hand TEXT,
    hitter_side TEXT,
    balls INT,
    strikes INT,
    zone_bucket TEXT,
    plate_x NUMERIC,
    plate_z NUMERIC,
    release_speed NUMERIC,
    release_spin_rate NUMERIC,
    release_extension NUMERIC,
    pfx_x NUMERIC,
    pfx_z NUMERIC,
    release_pos_x NUMERIC,
    release_pos_z NUMERIC,
    description TEXT,
    bb_type TEXT,
    launch_speed NUMERIC,
    launch_angle NUMERIC,
    hit_distance_sc NUMERIC,
    swing_flag BOOLEAN,
    whiff_flag BOOLEAN,
    in_play_flag BOOLEAN,
    hard_hit_flag BOOLEAN,
    estimated_woba_using_speedangle NUMERIC,
    run_value NUMERIC
);

CREATE TABLE IF NOT EXISTS pitcher_form_windows (
    form_window_id UUID PRIMARY KEY,
    pitcher_id TEXT NOT NULL REFERENCES players (player_id),
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    sample_pitch_count INT NOT NULL,
    profile_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hitter_tendency_profiles (
    profile_id UUID PRIMARY KEY,
    hitter_id TEXT NOT NULL REFERENCES players (player_id),
    season INT NOT NULL,
    split_key TEXT NOT NULL,
    profile_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matchup_requests (
    request_id UUID PRIMARY KEY,
    pitcher_id TEXT NOT NULL REFERENCES players (player_id),
    opponent_team_id TEXT NOT NULL,
    lineup_json JSONB NOT NULL,
    form_window_id UUID REFERENCES pitcher_form_windows (form_window_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_runs (
    simulation_id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES matchup_requests (request_id),
    model_version TEXT NOT NULL,
    iteration_count INT NOT NULL,
    result_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bullpen_sessions (
    session_id UUID PRIMARY KEY,
    pitcher_id TEXT NOT NULL REFERENCES players (player_id),
    session_date DATE NOT NULL,
    source TEXT NOT NULL,
    raw_file_uri TEXT,
    session_summary_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pitches_pitcher_game
    ON pitches (pitcher_id, game_id);

CREATE INDEX IF NOT EXISTS idx_pitches_hitter_game
    ON pitches (hitter_id, game_id);

CREATE INDEX IF NOT EXISTS idx_pitches_pitchtype_handedness
    ON pitches (pitch_type, pitcher_hand, hitter_side);

CREATE INDEX IF NOT EXISTS idx_plate_appearances_pitcher_hitter_game
    ON plate_appearances (pitcher_id, hitter_id, game_id);

CREATE INDEX IF NOT EXISTS idx_pitcher_form_windows_pitcher_window_end
    ON pitcher_form_windows (pitcher_id, window_end);

CREATE INDEX IF NOT EXISTS idx_hitter_tendency_profiles_hitter_split_season
    ON hitter_tendency_profiles (hitter_id, split_key, season);

CREATE INDEX IF NOT EXISTS idx_matchup_requests_pitcher_team_created
    ON matchup_requests (pitcher_id, opponent_team_id, created_at);
