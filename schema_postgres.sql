-- Optional: the app creates these tables itself via SQLAlchemy (init_db).
CREATE TABLE IF NOT EXISTS matches (
  id SERIAL PRIMARY KEY,
  bookmaker VARCHAR(20) NOT NULL,
  cycle_id INTEGER NOT NULL,
  round_no INTEGER NOT NULL,
  kickoff TIMESTAMP NOT NULL,
  home VARCHAR(60) NOT NULL, away VARCHAR(60) NOT NULL,
  odds_1 REAL, odds_x REAL, odds_2 REAL,
  odds_over25 REAL, odds_under25 REAL, odds_gg REAL, odds_ng REAL,
  home_goals INTEGER, away_goals INTEGER,
  CONSTRAINT uq_match UNIQUE (bookmaker, cycle_id, round_no, home, away)
);
CREATE INDEX IF NOT EXISTS ix_matches_cycle ON matches (cycle_id);
CREATE TABLE IF NOT EXISTS cycle_summary (
  bookmaker VARCHAR(20), cycle_id INTEGER,
  n_matches INTEGER, total_goals INTEGER, avg_goals REAL,
  home_win_pct REAL, draw_pct REAL, away_win_pct REAL, over25_pct REAL, btts_pct REAL,
  computed_at TIMESTAMP, PRIMARY KEY (bookmaker, cycle_id)
);
CREATE TABLE IF NOT EXISTS bets (
  id SERIAL PRIMARY KEY, bookmaker VARCHAR(20) NOT NULL, cycle_id INTEGER NOT NULL,
  round_no INTEGER NOT NULL, home VARCHAR(60) NOT NULL, away VARCHAR(60) NOT NULL,
  market VARCHAR(20), selection VARCHAR(10), odds REAL, model_prob REAL, ev REAL,
  stake REAL DEFAULT 1, status VARCHAR(10) DEFAULT 'open', pnl REAL, placed_at TIMESTAMP
);
