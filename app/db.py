import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('boss', 'scorer', 'team')),
    name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed')),
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    birth_date TEXT,
    cert_ok INTEGER NOT NULL DEFAULT 0,
    cert_file TEXT,
    cert_original_name TEXT,
    cert_uploaded_at TEXT
);
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    phase TEXT NOT NULL CHECK (phase IN ('group', 'main', 'cons')),
    group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    round INTEGER NOT NULL DEFAULT 0,
    round_label TEXT,
    team1_id INTEGER REFERENCES teams(id),
    team2_id INTEGER REFERENCES teams(id),
    score1 INTEGER NOT NULL DEFAULT 0,
    score2 INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'live', 'finished')),
    court INTEGER,
    start_time TEXT,
    seq INTEGER NOT NULL DEFAULT 0,
    next_match_id INTEGER,
    next_slot INTEGER,
    loser_next_match_id INTEGER,
    loser_next_slot INTEGER,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);
"""

DEFAULT_SETTINGS = {
    "tournament_name": "Torneo 3v3",
    "tournament_info": "",
    "registration_open": "1",
    "min_players": "4",
    "max_players": "8",
    "courts": "1",
    "match_minutes": "20",
    "start_time": "",
}


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def connect(path):
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(path):
    conn = connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(matches)")}
    for col in ("loser_next_match_id", "loser_next_slot"):  # database creati con la v1
        if col not in cols:
            conn.execute("ALTER TABLE matches ADD COLUMN %s INTEGER" % col)
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()
