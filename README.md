# Virtual League Analytics v2 (FastAPI + Tailwind + Chart.js)

For SportyBet / Betika virtual football: 30-minute macro cycles, 3-minute rounds.

## Layout
    app/
      main.py            FastAPI app (mounts /static, routers)
      config.py          settings (env-overridable)
      db.py              SQLAlchemy tables + queries (SQLite or PostgreSQL)
      schemas.py         request validation (Pydantic)
      routers/api.py     JSON API (docs at /docs)      routers/pages.py   HTML page
      services/          timers, ingest, analysis, model (Poisson), backtest,
                         ratings (team trends/radar), exporter (CSV), predictions, reports
      templates/         base.html, dashboard.html (Tailwind)
      static/js/app.js   dashboard logic + Chart.js charts
    scripts/seed_demo.py synthetic RNG data ("DEMO")     tests/test_api.py

## Setup
    python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
    pip install -r requirements.txt                       # add requirements-dev.txt for tests

Database: SQLite by default (`virtuals.db`, auto-created). For PostgreSQL:
    createdb virtuals && pip install psycopg2-binary
    export DATABASE_URL="postgresql+psycopg2://USER:PASS@localhost:5432/virtuals"
(`schema_postgres.sql` is the equivalent raw SQL; tables are also created automatically.)

## Run
    python -m scripts.seed_demo        # optional demo data, pick "DEMO" in the dropdown
    uvicorn app.main:app --reload      # or: python run.py
    open http://127.0.0.1:8000         # API docs: /docs
    pytest                             # optional
The page loads Tailwind and Chart.js from CDNs, so you need internet in the browser.

## Workflow
1. Press **Sync clock** when a round kicks off on the bookmaker's site (pick its round 1-10).
2. Before a round: paste fixtures + odds (Live tab). Predictions and value flags appear.
3. After it: Results tab, enter scores. Bets settle; cycle stats refresh.
4. Team ratings tab: attack/defence trend, radar vs league, all-team bars.
5. **Export History to CSV** (header) or `/api/export/history.csv?bookmaker=all`.
   Model columns are walk-forward (each cycle predicted only from earlier cycles).

## Key endpoints
    GET  /api/status                 current cycle/round + countdown data
    GET  /api/predictions            model probs, edge, EV, value flags for pending fixtures
    POST /api/matches[/bulk]         add fixtures/odds (and scores)
    POST /api/results                final scores for pending fixtures -> settles bets
    GET/POST /api/bets, POST /api/bets/track-value
    GET  /api/analysis  /api/performance  /api/backtest
    GET  /api/ratings/{trend,profile,league}
    GET  /api/export/history.csv  /api/export/bets.csv
