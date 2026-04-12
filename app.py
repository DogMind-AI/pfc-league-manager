"""
Pensacola FC League Manager
Multi-division youth soccer league dashboard with:
- U15 Boys / U15 Girls division toggle
- add/edit/delete matches
- add/edit teams
- official standings
- advanced power rankings
- Elo ratings
- strength of schedule
- weighted form index (last 5)
- goal differential momentum
- upset probability model
- projected table insights
- upcoming match predictions
- schedule manager (add games, reschedule, mark canceled/bye/played)
- password-protected admin editing
- PDF / PNG / CSV exports
- partial-count games (counts for both, home only, away only, or neither)
- playoff picture predictor (top 4 eligible teams)
"""

import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, datetime
import io
import os
import base64
import textwrap

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Pensacola FC League Manager",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = "league.db"
DIVISIONS = ["U15 Boys", "U15 Girls"]
ADMIN_PASSWORD = "cobras2026"

# counts_for options
COUNTS_OPTIONS = ["Both Teams", "Home Only", "Away Only", "Neither"]

# ─────────────────────────────────────────────
# NON-PFC TEAMS — excluded from all ranking/analytics displays
# Games against them still count toward PFC team standings.
# ─────────────────────────────────────────────
NON_PFC_TEAMS = {
    "U15 Boys": ["PSY T1", "PSYT2"],
    "U15 Girls": [],
}

def get_pfc_teams(division: str, all_teams: list[str]) -> list[str]:
    """Return only PFC-affiliated teams for a division (excludes non-PFC opponents)."""
    excluded = NON_PFC_TEAMS.get(division, [])
    return [t for t in all_teams if t not in excluded]


# ─────────────────────────────────────────────
# PLAYOFF CONFIG
# ─────────────────────────────────────────────
PLAYOFF_ELIGIBLE_TEAMS = {
    "U15 Boys": ["Beavers", "Cobras", "Vipers", "Los Locos", "Pelicans", "Athletico"],
    "U15 Girls": ["PSY City", "Shockwaves", "Tator Tots", "Team Seth"],
}
PLAYOFF_SPOTS = 4

DEFAULT_TEAMS = {
    "U15 Boys": [
        "Cobras",
        "Athletico",
        "Vipers",
        "PSY T1",
        "Beavers",
        "PSYT2",
        "Los Locos",
        "Pelicans",
    ],
    "U15 Girls": [
        "PSY City",
        "Shockwaves",
        "Tator Tots",
        "Team Seth",
    ],
}


# ─────────────────────────────────────────────
# TEAM NAME NORMALIZATION
# ─────────────────────────────────────────────
TEAM_NAME_ALIASES = {
    "Team Rick": "Shockwaves",
    "Shockwaves": "Shockwaves",
    "Tater Tots": "Tator Tots",
    "Tator Tots": "Tator Tots"
}

def normalize_team_name(name):
    return TEAM_NAME_ALIASES.get(name, name)


SCHEDULE_ROWS = {
    "U15 Boys": [
        {"week": 1, "game_date": "2026-03-07", "home_team": "Vipers", "away_team": "PSY T1", "location": "Field 4", "time": "9:00 AM"},
        {"week": 1, "game_date": "2026-03-07", "home_team": "Beavers", "away_team": "PSYT2", "location": "Field 4", "time": "10:30 AM"},
        {"week": 1, "game_date": "2026-03-07", "home_team": "Athletico", "away_team": "Cobras", "location": "Field 5", "time": "9:00 AM"},
        {"week": 1, "game_date": "2026-03-07", "home_team": "Pelicans", "away_team": "Los Locos", "location": "Field 4", "time": "12:00 PM"},

        {"week": 2, "game_date": "2026-03-14", "home_team": "Athletico", "away_team": "PSY T1", "location": "Field 4", "time": "9:00 AM"},
        {"week": 2, "game_date": "2026-03-14", "home_team": "Cobras", "away_team": "PSYT2", "location": "Field 4", "time": "10:30 AM"},
        {"week": 2, "game_date": "2026-03-14", "home_team": "Beavers", "away_team": "Pelicans", "location": "Field 3", "time": "10:30 AM"},

        {"week": 3, "game_date": "2026-03-20", "home_team": "Vipers", "away_team": "Los Locos", "location": "Field 5", "time": "6:00 PM"},
        {"week": 3, "game_date": "2026-03-21", "home_team": "Los Locos", "away_team": "PSY T1", "location": "Field 4", "time": "9:00 AM"},
        {"week": 3, "game_date": "2026-03-21", "home_team": "Pelicans", "away_team": "PSYT2", "location": "Field 4", "time": "10:30 AM"},
        {"week": 3, "game_date": "2026-03-21", "home_team": "Beavers", "away_team": "Cobras", "location": "Field 4", "time": "9:00 AM"},
        {"week": 3, "game_date": "2026-03-21", "home_team": "Vipers", "away_team": "Athletico", "location": "Field 3", "time": "12:00 PM"},

        {"week": 4, "game_date": "2026-04-03", "home_team": "Pelicans", "away_team": "Cobras", "location": "Field 4", "time": "7:00 PM"},
        {"week": 4, "game_date": "2026-04-03", "home_team": "Vipers", "away_team": "Beavers", "location": "Field 3", "time": "5:30 PM"},
        {"week": 4, "game_date": "2026-04-03", "home_team": "Athletico", "away_team": "Los Locos", "location": "Field 4", "time": "5:30 PM"},
        {"week": 4, "game_date": "2026-04-04", "home_team": "Cobras", "away_team": "PSY T1", "location": "Field 4", "time": "9:00 AM"},
        {"week": 4, "game_date": "2026-04-04", "home_team": "Los Locos", "away_team": "PSYT2", "location": "Field 4", "time": "10:30 AM"},
        {"week": 4, "game_date": "2026-04-04", "home_team": "Pelicans", "away_team": "Vipers", "location": "Field 5", "time": "9:00 AM"},
        {"week": 4, "game_date": "2026-04-04", "home_team": "Beavers", "away_team": "Athletico", "location": "Field 4", "time": "12:00 PM"},

        {"week": 5, "game_date": "2026-04-11", "home_team": "Vipers", "away_team": "PSY T1", "location": "Field 4", "time": "9:00 AM"},
        {"week": 5, "game_date": "2026-04-11", "home_team": "Beavers", "away_team": "PSYT2", "location": "Field 4", "time": "10:30 AM"},
        {"week": 5, "game_date": "2026-04-11", "home_team": "Athletico", "away_team": "Pelicans", "location": "Field 3", "time": "12:00 PM"},
        {"week": 5, "game_date": "2026-04-11", "home_team": "Cobras", "away_team": "Los Locos", "location": "Field 5", "time": "9:00 AM"},

        {"week": 6, "game_date": "2026-04-18", "home_team": "Pelicans", "away_team": "PSY T1", "location": "Field 4", "time": "9:00 AM"},
        {"week": 6, "game_date": "2026-04-18", "home_team": "Athletico", "away_team": "PSYT2", "location": "Field 4", "time": "10:30 AM"},
        {"week": 6, "game_date": "2026-04-18", "home_team": "Cobras", "away_team": "Vipers", "location": "Field 5", "time": "9:00 AM"},
        {"week": 6, "game_date": "2026-04-18", "home_team": "Los Locos", "away_team": "Beavers", "location": "Field 4", "time": "12:00 PM"},

        {"week": 7, "game_date": "2026-04-25", "home_team": "Cobras", "away_team": "PSY T1", "location": "Field 4", "time": "9:00 AM"},
        {"week": 7, "game_date": "2026-04-25", "home_team": "Beavers", "away_team": "PSYT2", "location": "Field 4", "time": "10:30 AM"},
        {"week": 7, "game_date": "2026-04-25", "home_team": "Vipers", "away_team": "Athletico", "location": "Field 4", "time": "12:00 PM"},
        {"week": 7, "game_date": "2026-04-25", "home_team": "Pelicans", "away_team": "Los Locos", "location": "Field 5", "time": "9:00 AM"},
    ],
    "U15 Girls": [
        {"week": 1, "game_date": "2026-03-07", "home_team": "Tator Tots", "away_team": "PSY City", "location": "Field 3", "time": "9:00 AM"},
        {"week": 1, "game_date": "2026-03-07", "home_team": "Team Seth", "away_team": "Shockwaves", "location": "Field 3", "time": "10:30 AM"},

        {"week": 2, "game_date": "2026-03-13", "home_team": "Team Seth", "away_team": "Tator Tots", "location": "Field 3", "time": "6:30 PM"},
        {"week": 2, "game_date": "2026-03-14", "home_team": "Shockwaves", "away_team": "PSY City", "location": "Field 3", "time": "9:00 AM"},

        {"week": 3, "game_date": "2026-03-21", "home_team": "Shockwaves", "away_team": "PSY City", "location": "Field 3", "time": "9:00 AM"},
        {"week": 3, "game_date": "2026-03-21", "home_team": "Tator Tots", "away_team": "Team Seth", "location": "Field 3", "time": "10:30 AM"},

        {"week": 4, "game_date": "2026-04-04", "home_team": "Team Seth", "away_team": "PSY City", "location": "Field 3", "time": "9:00 AM"},
        {"week": 4, "game_date": "2026-04-04", "home_team": "Tator Tots", "away_team": "Shockwaves", "location": "Field 3", "time": "10:30 AM"},

        {"week": 5, "game_date": "2026-04-11", "home_team": "Tator Tots", "away_team": "PSY City", "location": "Field 3", "time": "9:00 AM"},

        {"week": 6, "game_date": "2026-04-18", "home_team": "Shockwaves", "away_team": "PSY City", "location": "Field 3", "time": "9:00 AM"},
        {"week": 6, "game_date": "2026-04-18", "home_team": "Team Seth", "away_team": "Tator Tots", "location": "Field 3", "time": "10:30 AM"},

        {"week": 7, "game_date": "2026-04-25", "home_team": "Tator Tots", "away_team": "PSY City", "location": "Field 3", "time": "9:00 AM"},
        {"week": 7, "game_date": "2026-04-25", "home_team": "Shockwaves", "away_team": "Team Seth", "location": "Field 3", "time": "10:30 AM"},
    ],
}

LOGO_CANDIDATES = ["pfc_logo.png", "logo.png", "pensacola_fc_logo.png"]

PFC_NAVY = "#1B2F6B"
PFC_BLUE = "#3557A8"
PFC_LIGHT_BLUE = "#5F7FD1"
PFC_SILVER = "#A9ABB3"
PFC_LIGHT = "#F5F7FB"
PFC_WHITE = "#FFFFFF"
PFC_GREEN = "#2E8B57"
PFC_RED = "#C0392B"
PFC_GOLD = "#D4AF37"
PFC_AMBER = "#D99100"
PFC_DARK = "#0F1B3D"
PFC_ORANGE = "#E67E22"
PFC_PURPLE = "#7B52AB"


# ─────────────────────────────────────────────
# DATE / LOGO HELPERS
# ─────────────────────────────────────────────
def to_iso_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value):
        return ""
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return text


def format_display_date(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%m/%d/%Y")
        except ValueError:
            pass
    return text


def parse_to_date(value):
    text = to_iso_date(value)
    return datetime.strptime(text, "%Y-%m-%d").date()


def find_logo_path():
    for path in LOGO_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def get_logo_base64():
    logo_path = find_logo_path()
    if not logo_path:
        return None
    with open(logo_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def render_header(selected_division: str):
    logo_b64 = get_logo_base64()
    subtitle = f"{selected_division} Division Analytics Hub"
    if logo_b64:
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:8px;">
                <img src="data:image/png;base64,{logo_b64}" style="height:72px;">
                <div>
                    <div style="font-size:2rem;font-weight:900;color:{PFC_NAVY};line-height:1.1;">
                        Pensacola FC League Manager
                    </div>
                    <div style="color:{PFC_BLUE};font-weight:600;">
                        {subtitle}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:8px;">
                <div style="font-size:2.5rem;">⚽</div>
                <div>
                    <div style="font-size:2rem;font-weight:900;color:{PFC_NAVY};line-height:1.1;">
                        Pensacola FC League Manager
                    </div>
                    <div style="color:{PFC_BLUE};font-weight:600;">
                        {subtitle}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def column_exists(conn, table_name: str, column_name: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    cols = [row[1] for row in cur.fetchall()]
    return column_name in cols


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            division   TEXT DEFAULT 'U15 Boys',
            week       INTEGER NOT NULL,
            game_date  TEXT NOT NULL,
            home_team  TEXT NOT NULL,
            away_team  TEXT NOT NULL,
            home_goals INTEGER NOT NULL,
            away_goals INTEGER NOT NULL,
            notes      TEXT DEFAULT '',
            counts_for TEXT DEFAULT 'Both Teams'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            division  TEXT NOT NULL,
            team_name TEXT NOT NULL,
            UNIQUE(division, team_name)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS league_notes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            division  TEXT DEFAULT 'U15 Boys',
            created   TEXT NOT NULL,
            note_text TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            division   TEXT NOT NULL,
            week       INTEGER NOT NULL,
            game_date  TEXT NOT NULL,
            home_team  TEXT NOT NULL,
            away_team  TEXT NOT NULL,
            location   TEXT DEFAULT '',
            time       TEXT DEFAULT '',
            status     TEXT DEFAULT 'scheduled',
            notes      TEXT DEFAULT ''
        )
    """)

    conn.commit()

    # Migrations for existing databases
    if not column_exists(conn, "matches", "division"):
        c.execute("ALTER TABLE matches ADD COLUMN division TEXT DEFAULT 'U15 Boys'")
        conn.commit()

    if not column_exists(conn, "league_notes", "division"):
        c.execute("ALTER TABLE league_notes ADD COLUMN division TEXT DEFAULT 'U15 Boys'")
        conn.commit()

    if not column_exists(conn, "matches", "counts_for"):
        c.execute("ALTER TABLE matches ADD COLUMN counts_for TEXT DEFAULT 'Both Teams'")
        conn.commit()

    for division, teams in DEFAULT_TEAMS.items():
        for team in teams:
            c.execute(
                "INSERT OR IGNORE INTO teams (division, team_name) VALUES (?, ?)",
                (division, team),
            )
    conn.commit()

    c.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()

    already_purged = c.execute(
        "SELECT value FROM meta WHERE key='demo_purged'"
    ).fetchone()

    if not already_purged:
        c.execute("DELETE FROM matches")
        c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('demo_purged', '1')")
        conn.commit()

    # Seed schedule table from SCHEDULE_ROWS if empty
    for division, rows in SCHEDULE_ROWS.items():
        count = c.execute(
            "SELECT COUNT(*) FROM schedule WHERE division=?",
            (division,),
        ).fetchone()[0]
        if count == 0:
            for row in rows:
                c.execute(
                    """
                    INSERT INTO schedule (division, week, game_date, home_team, away_team, location, time, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', '')
                    """,
                    (
                        division,
                        row["week"],
                        to_iso_date(row["game_date"]),
                        row["home_team"],
                        row["away_team"],
                        row.get("location", ""),
                        row.get("time", ""),
                    ),
                )
            conn.commit()

    conn.close()


def load_division_teams(division: str) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT team_name FROM teams WHERE division=? ORDER BY team_name",
        (division,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def add_team(division: str, team_name: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO teams (division, team_name) VALUES (?, ?)",
        (division, team_name.strip()),
    )
    conn.commit()
    conn.close()


def rename_team(division: str, old_name: str, new_name: str):
    conn = get_conn()
    new_name = new_name.strip()
    conn.execute("UPDATE teams SET team_name=? WHERE division=? AND team_name=?", (new_name, division, old_name))
    conn.execute("UPDATE matches SET home_team=? WHERE division=? AND home_team=?", (new_name, division, old_name))
    conn.execute("UPDATE matches SET away_team=? WHERE division=? AND away_team=?", (new_name, division, old_name))
    conn.execute("UPDATE schedule SET home_team=? WHERE division=? AND home_team=?", (new_name, division, old_name))
    conn.execute("UPDATE schedule SET away_team=? WHERE division=? AND away_team=?", (new_name, division, old_name))
    conn.commit()
    conn.close()


def can_delete_team(division: str, team_name: str) -> bool:
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE division=? AND (home_team=? OR away_team=?)",
        (division, team_name, team_name),
    ).fetchone()[0]
    conn.close()
    return count == 0


def delete_team(division: str, team_name: str):
    conn = get_conn()
    conn.execute("DELETE FROM teams WHERE division=? AND team_name=?", (division, team_name))
    conn.commit()
    conn.close()


def load_matches(division: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM matches WHERE division=? ORDER BY week, game_date, id",
        conn,
        params=(division,),
    )
    conn.close()
    if not df.empty:
        df["game_date"] = df["game_date"].astype(str)
        df["home_team"] = df["home_team"].apply(normalize_team_name)
        df["away_team"] = df["away_team"].apply(normalize_team_name)
        if "counts_for" not in df.columns:
            df["counts_for"] = "Both Teams"
        df["counts_for"] = df["counts_for"].fillna("Both Teams")
    return df


def match_exists(division, week, game_date, home, away, hg, ag, exclude_id=None):
    conn = get_conn()
    query = """
        SELECT COUNT(*) FROM matches
        WHERE division=? AND week=? AND game_date=? AND home_team=? AND away_team=? AND home_goals=? AND away_goals=?
    """
    params = [division, int(week), to_iso_date(game_date), home, away, int(hg), int(ag)]
    if exclude_id is not None:
        query += " AND id <> ?"
        params.append(int(exclude_id))
    count = conn.execute(query, params).fetchone()[0]
    conn.close()
    return count > 0


def insert_match(division, week, game_date, home, away, hg, ag, notes, counts_for="Both Teams"):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO matches (division, week, game_date, home_team, away_team, home_goals, away_goals, notes, counts_for)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (division, int(week), to_iso_date(game_date), home, away, int(hg), int(ag), notes.strip(), counts_for),
    )
    conn.commit()
    conn.close()


def update_match(match_id, division, week, game_date, home, away, hg, ag, notes, counts_for="Both Teams"):
    conn = get_conn()
    conn.execute(
        """
        UPDATE matches
        SET division=?, week=?, game_date=?, home_team=?, away_team=?, home_goals=?, away_goals=?, notes=?, counts_for=?
        WHERE id=?
        """,
        (division, int(week), to_iso_date(game_date), home, away, int(hg), int(ag), notes.strip(), counts_for, int(match_id)),
    )
    conn.commit()
    conn.close()


def delete_match(match_id):
    conn = get_conn()
    conn.execute("DELETE FROM matches WHERE id=?", (int(match_id),))
    conn.commit()
    conn.close()


def load_notes(division: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM league_notes WHERE division=? ORDER BY id DESC",
        conn,
        params=(division,),
    )
    conn.close()
    return df


def insert_note(division: str, text: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO league_notes (division, created, note_text) VALUES (?,?,?)",
        (division, datetime.now().strftime("%Y-%m-%d %H:%M"), text),
    )
    conn.commit()
    conn.close()


def delete_note(note_id):
    conn = get_conn()
    conn.execute("DELETE FROM league_notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# SCHEDULE DB FUNCTIONS
# ─────────────────────────────────────────────
def load_schedule_from_db(division: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM schedule WHERE division=? ORDER BY week, game_date, time, home_team",
        conn,
        params=(division,),
    )
    conn.close()
    if not df.empty:
        df["game_date"] = df["game_date"].astype(str)
    return df


def load_schedule_df(division: str) -> pd.DataFrame:
    df = load_schedule_from_db(division)
    if df.empty:
        return pd.DataFrame(columns=["week", "game_date", "home_team", "away_team", "location", "time"])
    active = df[df["status"] == "scheduled"].copy()
    return active.sort_values(["week", "game_date", "time", "home_team"]).reset_index(drop=True)


def insert_schedule_game(division, week, game_date, home, away, location, time_str, notes=""):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO schedule (division, week, game_date, home_team, away_team, location, time, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)
        """,
        (division, int(week), to_iso_date(game_date), home, away, location.strip(), time_str.strip(), notes.strip()),
    )
    conn.commit()
    conn.close()


def update_schedule_game(game_id, week, game_date, home, away, location, time_str, status, notes):
    conn = get_conn()
    conn.execute(
        """
        UPDATE schedule
        SET week=?, game_date=?, home_team=?, away_team=?, location=?, time=?, status=?, notes=?
        WHERE id=?
        """,
        (int(week), to_iso_date(game_date), home, away, location.strip(), time_str.strip(), status, notes.strip(), int(game_id)),
    )
    conn.commit()
    conn.close()


def delete_schedule_game(game_id):
    conn = get_conn()
    conn.execute("DELETE FROM schedule WHERE id=?", (int(game_id),))
    conn.commit()
    conn.close()


def set_game_status(game_id: int, status: str, notes: str = ""):
    conn = get_conn()
    conn.execute(
        "UPDATE schedule SET status=?, notes=? WHERE id=?",
        (status, notes.strip(), int(game_id)),
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# ANALYTICS — counts_for aware
# ─────────────────────────────────────────────

def counts_for_team(counts_for: str, side: str) -> bool:
    if counts_for == "Both Teams":
        return True
    if counts_for == "Home Only":
        return side == "home"
    if counts_for == "Away Only":
        return side == "away"
    if counts_for == "Neither":
        return False
    return True


def normalize_series(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    min_v = s.min()
    max_v = s.max()
    if np.isclose(min_v, max_v):
        return pd.Series([50.0] * len(s), index=s.index)
    return (s - min_v) / (max_v - min_v) * 100


def weighted_last_n(values, weights=None):
    if not values:
        return 0.0
    if weights is None:
        weights = np.array([1, 2, 3, 4, 5], dtype=float)
    values = values[-len(weights):]
    weights = weights[-len(values):]
    values = np.array(values, dtype=float)
    return float(np.dot(values, weights) / weights.sum())


def compute_standings(df: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    """
    Compute standings for the given teams list only.
    Games against non-listed teams (PSY T1, PSYT2) still award points to
    the listed team — we just don't create a row for the non-listed team.
    """
    records = {t: dict(GP=0, W=0, D=0, L=0, GF=0, GA=0, GD_capped=0, Pts=0) for t in teams}

    for _, row in df.iterrows():
        h, a = row["home_team"], row["away_team"]
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        cf = row.get("counts_for", "Both Teams") or "Both Teams"

        home_counts = counts_for_team(cf, "home")
        away_counts = counts_for_team(cf, "away")

        raw_gd = hg - ag
        capped = int(np.clip(raw_gd, -4, 4))

        if hg > ag:
            home_result, away_result = "W", "L"
        elif hg < ag:
            home_result, away_result = "L", "W"
        else:
            home_result, away_result = "D", "D"

        # Only credit teams that are in our tracked list
        if home_counts and h in records:
            records[h]["GP"] += 1
            records[h]["GF"] += hg
            records[h]["GA"] += ag
            records[h]["GD_capped"] += capped
            if home_result == "W":
                records[h]["W"] += 1
                records[h]["Pts"] += 3
            elif home_result == "D":
                records[h]["D"] += 1
                records[h]["Pts"] += 1
            else:
                records[h]["L"] += 1

        if away_counts and a in records:
            records[a]["GP"] += 1
            records[a]["GF"] += ag
            records[a]["GA"] += hg
            records[a]["GD_capped"] -= capped
            if away_result == "W":
                records[a]["W"] += 1
                records[a]["Pts"] += 3
            elif away_result == "D":
                records[a]["D"] += 1
                records[a]["Pts"] += 1
            else:
                records[a]["L"] += 1

    rows = []
    for team, stats in records.items():
        rows.append({
            "Team": team,
            "GP": stats["GP"],
            "W": stats["W"],
            "D": stats["D"],
            "L": stats["L"],
            "GF": stats["GF"],
            "GA": stats["GA"],
            "GD": stats["GD_capped"],
            "Pts": stats["Pts"],
            "PPG": round(stats["Pts"] / stats["GP"], 2) if stats["GP"] else 0.0,
        })

    standings = pd.DataFrame(rows)
    standings = standings.sort_values(["Pts", "GD", "GF", "Team"], ascending=[False, False, False, True]).reset_index(drop=True)
    standings.index += 1
    standings.index.name = "Rank"
    return standings


def compute_standings_movement(df: pd.DataFrame, teams: list[str]) -> dict:
    if df.empty:
        return {t: 0 for t in teams}

    max_week = int(df["week"].max())
    prev_df = df[df["week"] < max_week]

    curr = compute_standings(df, teams).reset_index()
    curr_ranks = {r["Team"]: int(r["Rank"]) for _, r in curr.iterrows()}

    if prev_df.empty:
        return {t: 0 for t in teams}

    prev = compute_standings(prev_df, teams).reset_index()
    prev_ranks = {r["Team"]: int(r["Rank"]) for _, r in prev.iterrows()}

    return {team: prev_ranks.get(team, len(teams)) - curr_ranks.get(team, len(teams)) for team in teams}


def compute_power_package(df: pd.DataFrame, teams: list[str]):
    """
    Elo is computed using ALL teams in the match data (including PSY teams as opponents),
    but only the teams in the `teams` list are returned in rankings/analytics rows.
    This means Elo ratings for PFC teams correctly reflect games against PSY opponents.
    """
    # Collect all unique teams from match data to seed Elo (includes PSY as opponents)
    all_match_teams = set()
    if not df.empty:
        all_match_teams.update(df["home_team"].tolist())
        all_match_teams.update(df["away_team"].tolist())
    all_match_teams.update(teams)

    elo = {t: 1500.0 for t in all_match_teams}
    form_points = {t: [] for t in all_match_teams}
    raw_gd = {t: [] for t in all_match_teams}
    match_points = {t: [] for t in all_match_teams}
    opp_pre_elo = {t: [] for t in all_match_teams}
    results_text = {t: [] for t in all_match_teams}
    match_logs = []

    sorted_df = df.sort_values(["week", "game_date", "id"]).reset_index(drop=True)
    n_matches = len(sorted_df)

    for idx, row in sorted_df.iterrows():
        h, a = row["home_team"], row["away_team"]
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        match_date = row["game_date"]
        cf = row.get("counts_for", "Both Teams") or "Both Teams"

        home_counts = counts_for_team(cf, "home")
        away_counts = counts_for_team(cf, "away")

        pre_h = elo.get(h, 1500.0)
        pre_a = elo.get(a, 1500.0)

        exp_h = 1 / (1 + 10 ** ((pre_a - pre_h) / 400))
        exp_a = 1 - exp_h

        if hg > ag:
            act_h, act_a = 1.0, 0.0
            pts_h, pts_a = 3, 0
            winner = h
            res_h, res_a = "W", "L"
            underdog_win = pre_h < pre_a
        elif hg < ag:
            act_h, act_a = 0.0, 1.0
            pts_h, pts_a = 0, 3
            winner = a
            res_h, res_a = "L", "W"
            underdog_win = pre_a < pre_h
        else:
            act_h, act_a = 0.5, 0.5
            pts_h, pts_a = 1, 1
            winner = "Draw"
            res_h, res_a = "D", "D"
            underdog_win = abs(exp_h - 0.5) > 0.15

        goal_diff = abs(hg - ag)
        recency_w = 1.0 + 0.08 * (idx / max(n_matches - 1, 1))
        mov_mult = 1.0 + 0.10 * min(goal_diff, 8)
        upset_score = abs(act_h - exp_h)
        k = 32 * recency_w * mov_mult * (1 + upset_score)
        delta_h = k * (act_h - exp_h)
        delta_a = k * (act_a - exp_a)
        if h in elo:
            elo[h] += delta_h
        if a in elo:
            elo[a] += delta_a

        # Form/standings credit only to teams that count
        if home_counts and h in form_points:
            form_points[h].append(pts_h)
            match_points[h].append(pts_h)
            raw_gd[h].append(hg - ag)
            results_text[h].append(res_h)
            opp_pre_elo[h].append(pre_a)

        if away_counts and a in form_points:
            form_points[a].append(pts_a)
            match_points[a].append(pts_a)
            raw_gd[a].append(ag - hg)
            results_text[a].append(res_a)
            opp_pre_elo[a].append(pre_h)

        expected_winner = h if exp_h > exp_a else a if exp_a > exp_h else "Even"
        expected_winner_prob = max(exp_h, exp_a)
        actual_result_prob = exp_h if hg > ag else exp_a if hg < ag else (1 - abs(exp_h - 0.5))
        upset_probability = round((1 - actual_result_prob) * 100, 1)

        match_logs.append({
            "Week": int(row["week"]),
            "Date": match_date,
            "Home": h,
            "Away": a,
            "HG": hg,
            "AG": ag,
            "Score": f"{hg}-{ag}",
            "Winner": winner,
            "Counts For": cf,
            "Expected Winner": expected_winner,
            "Expected Winner Prob": round(expected_winner_prob * 100, 1),
            "Actual Result Prob": round(actual_result_prob * 100, 1),
            "Upset Probability": upset_probability,
            "Underdog Won": underdog_win,
            "Expected Home": round(exp_h, 3),
            "Expected Away": round(exp_a, 3),
            "Elo Swing Home": round(delta_h, 2),
            "Elo Swing Away": round(delta_a, 2),
            "Total Impact": round(abs(delta_h) + abs(delta_a), 2),
        })

    # Build output rows for PFC teams only
    rows = []
    for team in teams:
        form_index = weighted_last_n(form_points[team], np.array([1, 2, 3, 4, 5], dtype=float))
        gd_momentum = weighted_last_n(raw_gd[team], np.array([1, 2, 3, 4, 5], dtype=float))
        last5_form = "".join(results_text[team][-5:]) if results_text[team] else "—"
        sos = round(float(np.mean(opp_pre_elo[team])), 1) if opp_pre_elo[team] else 1500.0
        recent5_pts = sum(match_points[team][-5:]) if match_points[team] else 0

        power_score = (
            elo[team]
            + (form_index - 1.4) * 12
            + gd_momentum * 7
            + (recent5_pts - 6) * 1.2
        )

        rows.append({
            "Team": team,
            "Power Score": round(power_score, 1),
            "Elo Rating": round(elo[team], 1),
            "Form": last5_form,
            "Form Index": round(form_index, 2),
            "GD Momentum": round(gd_momentum, 2),
            "Strength of Schedule": sos,
            "Recent 5 Pts": recent5_pts,
        })

    pr = pd.DataFrame(rows).sort_values(["Power Score", "Elo Rating", "Team"], ascending=[False, False, True]).reset_index(drop=True)
    pr.index += 1
    pr.index.name = "Power Rank"

    match_analytics = pd.DataFrame(match_logs)
    standings = compute_standings(df, teams).reset_index()
    pr_reset = pr.reset_index()

    power_map = {r["Team"]: r["Power Score"] for _, r in pr_reset.iterrows()}
    elo_map = {r["Team"]: r["Elo Rating"] for _, r in pr_reset.iterrows()}
    form_map = {r["Team"]: r["Form Index"] for _, r in pr_reset.iterrows()}
    gdm_map = {r["Team"]: r["GD Momentum"] for _, r in pr_reset.iterrows()}
    sos_map = {r["Team"]: r["Strength of Schedule"] for _, r in pr_reset.iterrows()}

    analytics_rows = []
    for _, row in standings.iterrows():
        team = row["Team"]
        gp = int(row["GP"])

        gf_pg = round(row["GF"] / gp, 2) if gp else 0
        ga_pg = round(row["GA"] / gp, 2) if gp else 0

        gd_std = round(float(np.std(raw_gd[team])), 2) if raw_gd.get(team) else 0.0
        if gp <= 1:
            consistency = "Early"
        elif gd_std <= 1.2:
            consistency = "Steady"
        elif gd_std <= 2.4:
            consistency = "Balanced"
        else:
            consistency = "Volatile"

        form_index = form_map.get(team, 0)
        momentum = gdm_map.get(team, 0)

        if gp < 2:
            trend = "Early"
        elif momentum >= 1.5 and form_index >= 2.0:
            trend = "Surging"
        elif momentum <= -1.0 and form_index <= 1.0:
            trend = "Fading"
        else:
            trend = "Stable"

        analytics_rows.append({
            "Team": team,
            "Power Score": power_map.get(team, 1500),
            "Elo Rating": elo_map.get(team, 1500),
            "PPG": row["PPG"],
            "GF/Game": gf_pg,
            "GA/Game": ga_pg,
            "Strength of Schedule": sos_map.get(team, 1500),
            "Form Index": form_index,
            "GD Momentum": momentum,
            "Consistency": consistency,
            "Trend": trend,
        })

    team_analytics = pd.DataFrame(analytics_rows)
    team_analytics["PPG_Norm"] = normalize_series(team_analytics["PPG"])
    team_analytics["Power_Norm"] = normalize_series(team_analytics["Power Score"])
    team_analytics["Form_Norm"] = normalize_series(team_analytics["Form Index"])
    team_analytics["SOS_Norm"] = normalize_series(team_analytics["Strength of Schedule"])
    team_analytics["GDM_Norm"] = normalize_series(team_analytics["GD Momentum"])

    team_analytics["Projected Score"] = (
        team_analytics["Power_Norm"] * 0.35
        + team_analytics["PPG_Norm"] * 0.25
        + team_analytics["Form_Norm"] * 0.15
        + team_analytics["SOS_Norm"] * 0.10
        + team_analytics["GDM_Norm"] * 0.15
    ).round(1)

    team_analytics = team_analytics.sort_values(["Projected Score", "Power Score"], ascending=[False, False]).reset_index(drop=True)
    team_analytics["Projected Rank"] = np.arange(1, len(team_analytics) + 1)

    def assign_tier(rank):
        if rank <= 2:
            return "Contenders"
        elif rank <= 4:
            return "Chasing Pack"
        elif rank <= 6:
            return "Middle Pack"
        return "Rebuilding"

    team_analytics["Tier"] = team_analytics["Projected Rank"].apply(assign_tier)
    return pr, match_analytics, team_analytics


def compute_power_rankings(df: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    pr, _, _ = compute_power_package(df, teams)
    return pr


def compute_power_movement(df: pd.DataFrame, teams: list[str]) -> dict:
    if df.empty:
        return {t: 0 for t in teams}

    max_week = int(df["week"].max())
    prev_df = df[df["week"] < max_week]

    curr = compute_power_rankings(df, teams).reset_index()
    curr_ranks = {r["Team"]: int(r["Power Rank"]) for _, r in curr.iterrows()}

    if prev_df.empty:
        return {t: 0 for t in teams}

    prev = compute_power_rankings(prev_df, teams).reset_index()
    prev_ranks = {r["Team"]: int(r["Power Rank"]) for _, r in prev.iterrows()}

    return {team: prev_ranks.get(team, len(teams)) - curr_ranks.get(team, len(teams)) for team in teams}


def compute_current_metrics(df: pd.DataFrame, teams: list[str]):
    pr, _, analytics = compute_power_package(df, teams)
    pr_map = pr.set_index("Team").to_dict(orient="index")
    analytics_map = analytics.set_index("Team").to_dict(orient="index")
    return pr_map, analytics_map


def compute_upcoming_predictions(df: pd.DataFrame, division: str, teams: list[str]) -> pd.DataFrame:
    schedule_df = load_schedule_df(division)
    if schedule_df.empty:
        return schedule_df

    completed = set(
        zip(df["game_date"].astype(str), df["home_team"].astype(str), df["away_team"].astype(str))
    )
    upcoming = schedule_df[
        ~schedule_df.apply(lambda r: (str(r["game_date"]), str(r["home_team"]), str(r["away_team"])) in completed, axis=1)
    ].copy()

    if upcoming.empty:
        return upcoming

    # Only show upcoming games involving at least one PFC team
    upcoming = upcoming[
        upcoming["home_team"].isin(teams) | upcoming["away_team"].isin(teams)
    ].copy()

    if upcoming.empty:
        return upcoming

    pr_map, analytics_map = compute_current_metrics(df, teams)

    # Build a full Elo map including non-PFC teams as opponents
    all_match_teams = set()
    if not df.empty:
        all_match_teams.update(df["home_team"].tolist())
        all_match_teams.update(df["away_team"].tolist())
    full_elo = {t: 1500.0 for t in all_match_teams}
    # Use the elo from pr_map for PFC teams
    for t, v in pr_map.items():
        full_elo[t] = v.get("Elo Rating", 1500.0)

    records = []
    for _, row in upcoming.iterrows():
        home = row["home_team"]
        away = row["away_team"]

        home_elo = pr_map.get(home, {}).get("Elo Rating", full_elo.get(home, 1500.0))
        away_elo = pr_map.get(away, {}).get("Elo Rating", full_elo.get(away, 1500.0))
        home_form = analytics_map.get(home, {}).get("Form Index", 1.5)
        away_form = analytics_map.get(away, {}).get("Form Index", 1.5)
        home_gdm = analytics_map.get(home, {}).get("GD Momentum", 0.0)
        away_gdm = analytics_map.get(away, {}).get("GD Momentum", 0.0)
        home_sos = analytics_map.get(home, {}).get("Strength of Schedule", 1500.0)
        away_sos = analytics_map.get(away, {}).get("Strength of Schedule", 1500.0)

        blended_home = home_elo + 35 + (home_form - away_form) * 30 + (home_gdm - away_gdm) * 18 + (home_sos - away_sos) * 0.04
        blended_away = away_elo + (away_form - home_form) * 30 + (away_gdm - home_gdm) * 18 + (away_sos - home_sos) * 0.04
        diff = blended_home - blended_away

        home_win_prob = 1 / (1 + 10 ** (-diff / 400))
        away_win_prob = 1 - home_win_prob

        if home_win_prob >= away_win_prob:
            favorite = home
            favorite_prob = round(home_win_prob * 100, 1)
        else:
            favorite = away
            favorite_prob = round(away_win_prob * 100, 1)

        closeness = abs(home_win_prob - away_win_prob) * 100
        if closeness <= 10:
            upset_alert = "🔥 High"
        elif closeness <= 20:
            upset_alert = "⚠️ Moderate"
        else:
            upset_alert = "✅ Low"

        form_edge = home if home_form > away_form else away if away_form > home_form else "Even"

        records.append({
            "Week": int(row["week"]),
            "Date": format_display_date(row["game_date"]),
            "Time": row["time"],
            "Match": f"{home} vs {away}",
            "Favorite": favorite,
            "Favorite Win %": favorite_prob,
            "Home Win %": round(home_win_prob * 100, 1),
            "Away Win %": round(away_win_prob * 100, 1),
            "Upset Alert": upset_alert,
            "Form Edge": form_edge,
            "Location": row["location"],
            "Game Score": round(100 - closeness, 1),
        })

    return pd.DataFrame(records).sort_values(["Date", "Time", "Match"]).reset_index(drop=True)


# ─────────────────────────────────────────────
# PLAYOFF PICTURE
# ─────────────────────────────────────────────

def compute_playoff_picture(df: pd.DataFrame, division: str, teams: list[str]):
    eligible = PLAYOFF_ELIGIBLE_TEAMS.get(division, teams)

    full_standings = compute_standings(df, teams).reset_index()
    eligible_standings = full_standings[full_standings["Team"].isin(eligible)].copy()
    eligible_standings = eligible_standings.sort_values(
        ["Pts", "GD", "GF"], ascending=[False, False, False]
    ).reset_index(drop=True)
    eligible_standings.index += 1
    eligible_standings.index.name = "Playoff Rank"

    sched_df = load_schedule_from_db(division)
    completed_keys = set(
        zip(df["game_date"].astype(str), df["home_team"].astype(str), df["away_team"].astype(str))
    ) if not df.empty else set()

    # remaining_df = eligible vs eligible only (for head-to-head display and Monte Carlo)
    # remaining_counts = ALL remaining games per eligible team (for "X games left" and max pts)
    remaining = []
    remaining_counts = {t: 0 for t in eligible}

    if not sched_df.empty:
        for _, row in sched_df.iterrows():
            if row["status"] != "scheduled":
                continue
            key = (str(row["game_date"]), str(row["home_team"]), str(row["away_team"]))
            if key in completed_keys:
                continue
            h, a = row["home_team"], row["away_team"]
            # Count toward remaining games for any eligible team in the fixture
            if h in remaining_counts:
                remaining_counts[h] += 1
            if a in remaining_counts:
                remaining_counts[a] += 1
            # Only add to head-to-head display if BOTH teams are eligible
            if h in eligible and a in eligible:
                remaining.append(row)

    remaining_df = pd.DataFrame(remaining) if remaining else pd.DataFrame()

    current_pts = {row["Team"]: int(row["Pts"]) for _, row in eligible_standings.iterrows()}
    current_gd  = {row["Team"]: int(row["GD"]) for _, row in eligible_standings.iterrows()}
    current_gf  = {row["Team"]: int(row["GF"]) for _, row in eligible_standings.iterrows()}
    max_possible = {t: current_pts.get(t, 0) + remaining_counts[t] * 3 for t in eligible}

    sorted_pts = sorted(current_pts.values(), reverse=True)
    cutoff_pts = sorted_pts[PLAYOFF_SPOTS - 1] if len(sorted_pts) >= PLAYOFF_SPOTS else 0

    sorted_teams_by_pts = sorted(current_pts.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_teams_by_pts) > PLAYOFF_SPOTS:
        fifth_team = sorted_teams_by_pts[PLAYOFF_SPOTS][0]
        fifth_max = max_possible.get(fifth_team, 0)
    else:
        fifth_max = 0

    clinched = []
    eliminated = []
    bubble = []

    for team in eligible:
        pts = current_pts.get(team, 0)
        max_pts = max_possible.get(team, 0)

        if len(sorted_teams_by_pts) > PLAYOFF_SPOTS and pts > fifth_max:
            clinched.append(team)
        elif max_pts < cutoff_pts:
            eliminated.append(team)
        else:
            bubble.append(team)

    pr, _, analytics = compute_power_package(df, teams)
    pr_map = pr.set_index("Team").to_dict(orient="index")
    analytics_map = analytics.set_index("Team").to_dict(orient="index")

    # ── Build per-game win probabilities for remaining eligible matchups ──
    game_probs = []  # list of (home, away, h_win_p, draw_p, a_win_p)
    if not remaining_df.empty:
        for _, row in remaining_df.iterrows():
            h, a = row["home_team"], row["away_team"]
            if h not in eligible or a not in eligible:
                continue

            h_elo = pr_map.get(h, {}).get("Elo Rating", 1500.0)
            a_elo = pr_map.get(a, {}).get("Elo Rating", 1500.0)
            h_form = analytics_map.get(h, {}).get("Form Index", 1.5)
            a_form = analytics_map.get(a, {}).get("Form Index", 1.5)
            h_gdm = analytics_map.get(h, {}).get("GD Momentum", 0.0)
            a_gdm = analytics_map.get(a, {}).get("GD Momentum", 0.0)

            blended_h = h_elo + 35 + (h_form - a_form) * 30 + (h_gdm - a_gdm) * 18
            blended_a = a_elo + (a_form - h_form) * 30 + (a_gdm - h_gdm) * 18
            diff = blended_h - blended_a

            h_win_raw = 1 / (1 + 10 ** (-diff / 400))
            draw_p = 0.22
            h_win_p = h_win_raw * (1 - draw_p)
            a_win_p = (1 - h_win_raw) * (1 - draw_p)
            game_probs.append((h, a, h_win_p, draw_p, a_win_p))

    # ── Monte Carlo: simulate season N times, count top-4 finishes ────────
    N_SIMS = 2000
    rng = np.random.default_rng(42)
    playoff_counts = {t: 0 for t in eligible}

    for _ in range(N_SIMS):
        sim_pts = {t: current_pts.get(t, 0) for t in eligible}
        sim_gd  = {t: current_gd.get(t, 0)  for t in eligible}
        sim_gf  = {t: current_gf.get(t, 0)  for t in eligible}

        for h, a, h_win_p, draw_p, a_win_p in game_probs:
            r = rng.random()
            if r < h_win_p:
                sim_pts[h] += 3
                # simulate a plausible scoreline for GD tiebreaker
                goals = rng.integers(1, 4)
                sim_gd[h] += goals; sim_gd[a] -= goals
                sim_gf[h] += goals
            elif r < h_win_p + draw_p:
                sim_pts[h] += 1; sim_pts[a] += 1
                goals = rng.integers(0, 3)
                sim_gf[h] += goals; sim_gf[a] += goals
            else:
                sim_pts[a] += 3
                goals = rng.integers(1, 4)
                sim_gd[a] += goals; sim_gd[h] -= goals
                sim_gf[a] += goals

        # Rank by FIFA method: Pts → GD → GF → random tiebreak (alphabetical in real FIFA)
        sim_order = sorted(
            eligible,
            key=lambda t: (sim_pts[t], sim_gd[t], sim_gf[t], rng.random()),
            reverse=True,
        )
        for i, t in enumerate(sim_order):
            if i < PLAYOFF_SPOTS:
                playoff_counts[t] += 1

    playoff_pct = {t: round(playoff_counts[t] / N_SIMS * 100, 1) for t in eligible}

    # Override with 100% / 0% for mathematically decided teams
    for t in clinched:
        playoff_pct[t] = 100.0
    for t in eliminated:
        playoff_pct[t] = 0.0

    # ── Projected pts (deterministic expected-value pass) ─────────────────
    projected_pts = {t: float(current_pts.get(t, 0)) for t in eligible}
    for h, a, h_win_p, draw_p, a_win_p in game_probs:
        projected_pts[h] = projected_pts.get(h, 0) + round(h_win_p * 3 + draw_p * 1, 2)
        projected_pts[a] = projected_pts.get(a, 0) + round(a_win_p * 3 + draw_p * 1, 2)

    projected_rows = []
    for team in eligible:
        proj = round(projected_pts.get(team, 0), 1)
        curr = current_pts.get(team, 0)
        if team in clinched:
            status = "🏆 Clinched"
        elif team in eliminated:
            status = "❌ Eliminated"
        else:
            status = "🔥 Bubble"

        projected_rows.append({
            "Team": team,
            "Current Pts": curr,
            "Projected Pts": proj,
            "Playoff %": playoff_pct.get(team, 0.0),
            "Remaining Games": remaining_counts.get(team, 0),
            "Max Possible Pts": max_possible.get(team, 0),
            "Status": status,
        })

    projected_df = pd.DataFrame(projected_rows).sort_values(
        ["Projected Pts", "Current Pts"], ascending=[False, False]
    ).reset_index(drop=True)
    projected_df.index += 1
    projected_df.index.name = "Proj Rank"

    return {
        "current": eligible_standings,
        "projected": projected_df,
        "clinched": clinched,
        "eliminated": eliminated,
        "bubble": bubble,
        "remaining_games": remaining_counts,
        "remaining_df": remaining_df,
        "playoff_pct": playoff_pct,
    }


def render_playoff_picture(df: pd.DataFrame, division: str, teams: list[str]):
    eligible = PLAYOFF_ELIGIBLE_TEAMS.get(division, [])
    if not eligible:
        return

    st.markdown('<div class="section-header">🏟️ Playoff Picture</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No match results logged yet. Playoff projections will appear once games are recorded.")
        return

    pp = compute_playoff_picture(df, division, teams)
    projected = pp["projected"].reset_index()
    clinched = pp["clinched"]
    eliminated = pp["eliminated"]
    bubble = pp["bubble"]
    remaining_df = pp["remaining_df"]
    playoff_pct = pp["playoff_pct"]

    st.markdown(
        f"""
        <div style="background:{PFC_NAVY};border-radius:14px;padding:14px 22px;
            display:flex;align-items:center;gap:18px;margin-bottom:16px;">
            <span style="font-size:2rem;">🏆</span>
            <div>
                <div style="color:{PFC_GOLD};font-weight:900;font-size:1.1rem;">
                    Top 4 eligible teams advance to playoffs
                </div>
                <div style="color:{PFC_SILVER};font-size:0.85rem;margin-top:3px;">
                    PSY T1 and PSY T2 are excluded from playoff contention &nbsp;·&nbsp;
                    6 teams competing for 4 spots
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    chip_cols = st.columns(len(eligible))

    for i, row in projected.iterrows():
        team = row["Team"]
        proj_rank = int(row["Proj Rank"])
        curr_pts = int(row["Current Pts"])
        proj_pts = float(row["Projected Pts"])
        remaining = int(row["Remaining Games"])
        pct = playoff_pct.get(team, row.get("Playoff %", 0.0))

        in_playoffs = proj_rank <= PLAYOFF_SPOTS

        if team in clinched:
            bg = f"linear-gradient(160deg, {PFC_GREEN} 0%, #1A5E35 100%)"
            icon = "✅"
            label = "CLINCHED"
        elif team in eliminated:
            bg = f"linear-gradient(160deg, {PFC_RED} 0%, #7B1A1A 100%)"
            icon = "❌"
            label = "OUT"
        else:
            bg = f"linear-gradient(160deg, {PFC_AMBER} 0%, #8A5A00 100%)"
            icon = "🔥"
            label = "BUBBLE"

        border = f"3px solid {PFC_GOLD}" if in_playoffs else "3px solid rgba(255,255,255,0.15)"
        rank_label = f"#{proj_rank} Projected"

        # Playoff % bar fill color
        if pct >= 75:
            pct_color = PFC_GREEN
        elif pct >= 40:
            pct_color = PFC_AMBER
        else:
            pct_color = PFC_RED

        chip_cols[i].markdown(
            f"""
            <div style="background:{bg};border:{border};border-radius:16px;
                padding:16px 10px;text-align:center;margin:2px;
                box-shadow:0 6px 18px rgba(0,0,0,.22);">
                <div style="font-size:1.5rem;line-height:1;">{icon}</div>
                <div style="font-weight:900;font-size:0.95rem;color:white;margin:6px 0 2px 0;
                    letter-spacing:0.02em;">{team}</div>
                <div style="font-size:0.78rem;color:rgba(255,255,255,0.75);">{rank_label}</div>
                <div style="margin-top:8px;background:rgba(0,0,0,0.2);border-radius:8px;padding:5px 4px;">
                    <div style="color:white;font-size:0.8rem;">
                        <b>{curr_pts}</b> pts &rarr; <b style="color:{PFC_GOLD};">{proj_pts}</b>
                    </div>
                    <div style="color:rgba(255,255,255,0.65);font-size:0.72rem;">{remaining} games left</div>
                </div>
                <div style="margin-top:8px;background:rgba(0,0,0,0.25);border-radius:8px;padding:6px 6px 4px 6px;">
                    <div style="color:rgba(255,255,255,0.7);font-size:0.68rem;margin-bottom:3px;">PLAYOFF ODDS</div>
                    <div style="background:rgba(255,255,255,0.15);border-radius:5px;height:7px;overflow:hidden;margin-bottom:3px;">
                        <div style="width:{min(pct,100):.0f}%;height:100%;background:{pct_color};border-radius:5px;"></div>
                    </div>
                    <div style="color:white;font-weight:900;font-size:1rem;">{pct:.0f}%</div>
                </div>
                <div style="margin-top:6px;background:rgba(255,255,255,0.15);border-radius:6px;
                    padding:2px 6px;font-size:0.72rem;font-weight:900;color:white;">{label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

    left_col, right_col = st.columns(2)

    with left_col:
        st.markdown(
            f"<div style='font-weight:900;font-size:1rem;color:{PFC_NAVY};margin-bottom:10px;'>"
            f"📊 Current Playoff Standing</div>",
            unsafe_allow_html=True,
        )
        current = pp["current"].reset_index()

        for _, row in current.iterrows():
            rank = int(row["Playoff Rank"])
            team = row["Team"]
            pts = int(row["Pts"])
            gd = int(row["GD"])
            gp = int(row["GP"])
            wdl = f"{int(row['W'])}W {int(row['D'])}D {int(row['L'])}L"

            in_zone = rank <= PLAYOFF_SPOTS
            bg = f"linear-gradient(90deg, {PFC_NAVY} 0%, {PFC_BLUE} 100%)" if in_zone else "linear-gradient(90deg, #3A3A4A, #555568)"
            border_left = f"5px solid {PFC_GOLD}" if in_zone else f"5px solid {PFC_SILVER}"
            zone_badge = (
                f'<span style="background:{PFC_GOLD};color:{PFC_NAVY};font-size:0.68rem;'
                f'font-weight:900;padding:2px 7px;border-radius:5px;margin-left:4px;">IN</span>'
                if in_zone else
                f'<span style="background:{PFC_SILVER};color:white;font-size:0.68rem;'
                f'font-weight:900;padding:2px 7px;border-radius:5px;margin-left:4px;">OUT</span>'
            )

            divider = (
                f'<div style="border-top:2px dashed {PFC_GOLD};margin:5px 0;opacity:0.5;"></div>'
                if rank == PLAYOFF_SPOTS else ""
            )

            st.markdown(
                f"""
                <div style="background:{bg};border-left:{border_left};border-radius:10px;
                    padding:11px 16px;margin:4px 0;display:flex;align-items:center;gap:10px;
                    box-shadow:0 3px 10px rgba(0,0,0,.12);">
                    <div style="color:{PFC_GOLD};font-weight:900;font-size:1.1rem;min-width:30px;">
                        #{rank}
                    </div>
                    <div style="color:white;font-weight:800;flex:1;font-size:0.95rem;">{team}</div>
                    <div style="color:rgba(255,255,255,0.65);font-size:0.75rem;">{wdl}</div>
                    <div style="color:rgba(255,255,255,0.7);font-size:0.78rem;">GD {gd:+d}</div>
                    <div style="color:{PFC_GOLD};font-weight:900;font-size:1rem;">{pts}pts</div>
                    {zone_badge}
                </div>
                {divider}
                """,
                unsafe_allow_html=True,
            )

    with right_col:
        st.markdown(
            f"<div style='font-weight:900;font-size:1rem;color:{PFC_NAVY};margin-bottom:10px;'>"
            f"🔮 Projected Final Standings</div>",
            unsafe_allow_html=True,
        )

        for _, row in projected.iterrows():
            rank = int(row["Proj Rank"])
            team = row["Team"]
            curr_pts = int(row["Current Pts"])
            proj_pts = float(row["Projected Pts"])
            remaining = int(row["Remaining Games"])
            pct = playoff_pct.get(team, row.get("Playoff %", 0.0))

            in_zone = rank <= PLAYOFF_SPOTS
            bg = f"linear-gradient(90deg, {PFC_NAVY} 0%, {PFC_BLUE} 100%)" if in_zone else "linear-gradient(90deg, #3A3A4A, #555568)"
            border_left = f"5px solid {PFC_GOLD}" if in_zone else f"5px solid {PFC_SILVER}"

            if team in clinched:
                status_chip = (
                    f'<span style="background:{PFC_GREEN};color:white;font-size:0.68rem;'
                    f'font-weight:900;padding:2px 7px;border-radius:5px;">CLINCHED</span>'
                )
            elif team in eliminated:
                status_chip = (
                    f'<span style="background:{PFC_RED};color:white;font-size:0.68rem;'
                    f'font-weight:900;padding:2px 7px;border-radius:5px;">ELIM</span>'
                )
            else:
                status_chip = (
                    f'<span style="background:{PFC_AMBER};color:white;font-size:0.68rem;'
                    f'font-weight:900;padding:2px 7px;border-radius:5px;">BUBBLE</span>'
                )

            if pct >= 75:
                pct_color = PFC_GREEN
            elif pct >= 40:
                pct_color = PFC_AMBER
            else:
                pct_color = PFC_RED

            divider = (
                f'<div style="border-top:2px dashed {PFC_GOLD};margin:5px 0;opacity:0.5;"></div>'
                if rank == PLAYOFF_SPOTS else ""
            )

            pts_trend = f"{curr_pts} → {proj_pts}"

            st.markdown(
                f"""
                <div style="background:{bg};border-left:{border_left};border-radius:10px;
                    padding:11px 16px;margin:4px 0;display:flex;align-items:center;gap:10px;
                    box-shadow:0 3px 10px rgba(0,0,0,.12);">
                    <div style="color:{PFC_GOLD};font-weight:900;font-size:1.1rem;min-width:30px;">#{rank}</div>
                    <div style="color:white;font-weight:800;flex:1;font-size:0.95rem;">{team}</div>
                    <div style="color:rgba(255,255,255,0.65);font-size:0.75rem;">{remaining}G left</div>
                    <div style="color:white;font-size:0.82rem;">{pts_trend}</div>
                    <div style="min-width:52px;text-align:right;">
                        <span style="background:{pct_color};color:white;font-size:0.75rem;
                            font-weight:900;padding:2px 7px;border-radius:5px;">{pct:.0f}%</span>
                    </div>
                    {status_chip}
                </div>
                {divider}
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

    if not remaining_df.empty:
        st.markdown(
            f"<div style='font-weight:900;font-size:1rem;color:{PFC_NAVY};margin-bottom:8px;'>"
            f"🗓️ Remaining Playoff-Relevant Matchups</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="info-strip">These are the remaining scheduled games between the 6 playoff-eligible teams. '
            f'Every result directly shifts the playoff picture.</div>',
            unsafe_allow_html=True,
        )

        for _, row in remaining_df.sort_values(["game_date", "time"]).iterrows():
            h = row["home_team"]
            a = row["away_team"]
            date_str = format_display_date(row["game_date"])
            time_str = row.get("time", "")
            loc_str = row.get("location", "")
            week_num = int(row["week"])

            if h in clinched:
                h_color = PFC_GREEN
                h_tag = "✅"
            elif h in eliminated:
                h_color = PFC_RED
                h_tag = "❌"
            else:
                h_color = PFC_AMBER
                h_tag = "🔥"

            if a in clinched:
                a_color = PFC_GREEN
                a_tag = "✅"
            elif a in eliminated:
                a_color = PFC_RED
                a_tag = "❌"
            else:
                a_color = PFC_AMBER
                a_tag = "🔥"

            st.markdown(
                f"""
                <div style="background:white;border:1px solid #DCE5FF;border-radius:10px;
                    padding:11px 18px;margin:5px 0;display:flex;align-items:center;gap:14px;
                    box-shadow:0 2px 8px rgba(0,0,0,.05);">
                    <div style="background:{PFC_NAVY};color:{PFC_GOLD};font-weight:900;
                        font-size:0.8rem;padding:4px 10px;border-radius:8px;min-width:54px;
                        text-align:center;">Wk {week_num}</div>
                    <div style="color:#555;font-size:0.82rem;min-width:110px;">{date_str} {time_str}</div>
                    <div style="font-weight:900;color:{h_color};flex:1;font-size:0.95rem;">
                        {h_tag} {h}
                    </div>
                    <div style="color:{PFC_NAVY};font-weight:800;font-size:0.9rem;">vs</div>
                    <div style="font-weight:900;color:{a_color};flex:1;text-align:right;font-size:0.95rem;">
                        {a} {a_tag}
                    </div>
                    <div style="color:#999;font-size:0.78rem;min-width:58px;text-align:right;">{loc_str}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f'<div class="info-strip">✅ All playoff-relevant matchups have been played.</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap;align-items:center;">
            <span style="color:{PFC_DARK};font-weight:700;font-size:0.82rem;">Legend:</span>
            <span style="background:{PFC_GREEN};color:white;padding:4px 12px;border-radius:8px;
                font-size:0.78rem;font-weight:700;">✅ Clinched — mathematically in</span>
            <span style="background:{PFC_AMBER};color:white;padding:4px 12px;border-radius:8px;
                font-size:0.78rem;font-weight:700;">🔥 Bubble — still in contention</span>
            <span style="background:{PFC_RED};color:white;padding:4px 12px;border-radius:8px;
                font-size:0.78rem;font-weight:700;">❌ Eliminated — cannot qualify</span>
            <span style="border:2px solid {PFC_GOLD};color:{PFC_NAVY};padding:4px 12px;border-radius:8px;
                font-size:0.78rem;font-weight:700;">🏆 Gold border = projected playoff spot</span>
        </div>
        <div class="info-strip" style="margin-top:10px;">
            <b>How projections work:</b> Projected pts use the same Elo + form + GD momentum model
            as upcoming match predictions. Each remaining game is assigned probabilistic expected points
            (win prob × 3 + draw prob × 1). These are estimates — not guarantees.<br>
            <b>Playoff % methodology:</b> 2,000 season simulations run using Elo-derived win probabilities
            for every remaining eligible matchup. Each sim applies the FIFA tiebreaker order (Pts → GD → GF)
            to determine the top 4. The % reflects how often each team finishes in the top 4 across all sims.
            Clinched teams show 100%, eliminated teams show 0%.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────
def form_badge_html(form_str: str) -> str:
    colors_map = {"W": PFC_GREEN, "D": PFC_AMBER, "L": PFC_RED}
    html = []
    for ch in form_str:
        bg = colors_map.get(ch, PFC_SILVER)
        html.append(
            f'<span style="background:{bg};color:white;padding:3px 7px;border-radius:6px;font-weight:800;margin-right:4px;font-size:12px;">{ch}</span>'
        )
    return "".join(html) if html else '<span style="color:#666;">—</span>'


def movement_arrow(delta: int) -> str:
    if delta > 0:
        return f"▲ {delta}"
    elif delta < 0:
        return f"▼ {abs(delta)}"
    return "—"


def movement_color(delta: int) -> str:
    if delta > 0:
        return PFC_GREEN
    elif delta < 0:
        return PFC_RED
    return PFC_SILVER


def prep_match_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["game_date"] = out["game_date"].apply(format_display_date)
    return out


def status_badge(status: str) -> str:
    if status == "canceled":
        return f'<span style="background:{PFC_RED};color:white;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;">CANCELED</span>'
    elif status == "bye":
        return f'<span style="background:{PFC_ORANGE};color:white;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;">BYE</span>'
    elif status == "played":
        return f'<span style="background:{PFC_SILVER};color:white;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;">PLAYED</span>'
    return f'<span style="background:{PFC_GREEN};color:white;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;">SCHEDULED</span>'


def counts_for_badge(counts_for: str) -> str:
    if counts_for == "Both Teams" or not counts_for:
        return ""
    if counts_for == "Home Only":
        return f'<span style="background:{PFC_PURPLE};color:white;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;margin-left:6px;">HOME ONLY</span>'
    if counts_for == "Away Only":
        return f'<span style="background:{PFC_BLUE};color:white;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;margin-left:6px;">AWAY ONLY</span>'
    if counts_for == "Neither":
        return f'<span style="background:{PFC_DARK};color:white;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;margin-left:6px;">FRIENDLY</span>'
    return ""


# ─────────────────────────────────────────────
# EXPORT HELPERS
# ─────────────────────────────────────────────
def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def make_power_rankings_png(pr: pd.DataFrame, movement: dict, division: str) -> bytes:
    width = 1400
    row_h = 105
    header_h = 190
    footer_h = 130
    height = header_h + len(pr) * row_h + footer_h + 40

    img = Image.new("RGB", (width, height), PFC_LIGHT)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 54)
        font_sub = ImageFont.truetype("DejaVuSans.ttf", 24)
        font_rank = ImageFont.truetype("DejaVuSans-Bold.ttf", 44)
        font_team = ImageFont.truetype("DejaVuSans-Bold.ttf", 32)
        font_meta = ImageFont.truetype("DejaVuSans.ttf", 21)
    except:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_rank = ImageFont.load_default()
        font_team = ImageFont.load_default()
        font_meta = ImageFont.load_default()

    draw.rectangle([0, 0, width, header_h], fill=PFC_NAVY)
    draw.text((40, 28), f"{division.upper()} POWER RANKINGS", fill=PFC_WHITE, font=font_title)
    draw.text((44, 100), "Pensacola FC analytics snapshot", fill="#D9E3FF", font=font_sub)

    y = header_h + 18
    pr_reset = pr.reset_index()
    team_bar_colors = [PFC_BLUE, PFC_NAVY, "#2E4C95", "#4966B0", "#5977C1", "#6A88CF", "#809BDA", "#97AFEA"]

    for i, row in pr_reset.iterrows():
        bar_color = team_bar_colors[i % len(team_bar_colors)]
        draw.rounded_rectangle([35, y, width - 35, y + 82], radius=18, fill=bar_color)
        draw.text((70, y + 15), f"{int(row['Power Rank'])}.", fill=PFC_WHITE, font=font_rank)
        draw.text((180, y + 14), str(row["Team"]).upper(), fill=PFC_WHITE, font=font_team)
        move = movement.get(row["Team"], 0)
        draw.text((width - 290, y + 16), movement_arrow(move), fill=movement_color(move), font=font_team)
        meta = (
            f"Power {row['Power Score']}   |   Elo {row['Elo Rating']}   |   "
            f"Form {row['Form']}   |   GDM {row['GD Momentum']}"
        )
        draw.text((182, y + 50), meta, fill="#E9EEFF", font=font_meta)
        y += row_h

    footer = (
        "Power rankings blend Elo rating, weighted form index, strength of schedule, "
        "goal differential momentum, upset impact, and scoring margin. "
        "They are analytical only and separate from official standings."
    )
    wrapped = textwrap.fill(footer, width=115)
    draw.multiline_text((40, height - 95), wrapped, fill=PFC_DARK, font=font_meta, spacing=6)

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def make_league_summary_pdf(division, standings, pr, recent_results, analytics_df) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), leftMargin=30, rightMargin=30, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    story = []

    story.extend([
        Paragraph(f"<b>Pensacola FC League Summary - {division}</b>", styles["Title"]),
        Paragraph(f"Generated on {datetime.now().strftime('%m/%d/%Y %I:%M %p')}", styles["Normal"]),
        Spacer(1, 12),
    ])

    def make_table(df_table, title_text):
        story.append(Paragraph(f"<b>{title_text}</b>", styles["Heading2"]))
        table_data = [list(df_table.columns)] + df_table.astype(str).values.tolist()
        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PFC_NAVY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F7F9FE"), colors.HexColor("#EEF3FD")]),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 14))

    make_table(standings.reset_index()[["Rank", "Team", "GP", "W", "D", "L", "GF", "GA", "GD", "Pts"]], "Official Standings")
    make_table(pr.reset_index()[["Power Rank", "Team", "Power Score", "Elo Rating", "Form", "Form Index", "GD Momentum"]], "Power Rankings")
    make_table(analytics_df[["Team", "Strength of Schedule", "Form Index", "GD Momentum", "Trend", "Projected Rank", "Tier"]], "Advanced Analytics")
    if not recent_results.empty:
        make_table(recent_results.head(8), "Recent Results")

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def make_dashboard_pdf(division: str, df: pd.DataFrame, teams: list[str]) -> bytes:
    standings = compute_standings(df, teams)
    pr, _, analytics_df = compute_power_package(df, teams)
    upcoming = compute_upcoming_predictions(df, division, teams)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), leftMargin=25, rightMargin=25, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    story = []

    story.extend([
        Paragraph(f"<b>Pensacola FC Dashboard Export - {division}</b>", styles["Title"]),
        Paragraph(f"Generated on {datetime.now().strftime('%m/%d/%Y %I:%M %p')}", styles["Normal"]),
        Spacer(1, 12),
    ])

    total_goals = int(df["home_goals"].sum() + df["away_goals"].sum()) if not df.empty else 0
    avg_goals = round(total_goals / max(len(df), 1), 1) if not df.empty else 0
    current_week = int(df["week"].max()) if not df.empty else 0

    def make_table(df_table, title_text):
        story.append(Paragraph(f"<b>{title_text}</b>", styles["Heading2"]))
        table_data = [list(df_table.columns)] + df_table.astype(str).values.tolist()
        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PFC_NAVY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F7F9FE"), colors.HexColor("#EEF3FD")]),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 12))

    make_table(pd.DataFrame([{"Matches Played": len(df), "Week": current_week, "Total Goals": total_goals, "Avg Goals/Match": avg_goals}]), "Summary")
    make_table(standings.reset_index()[["Rank", "Team", "GP", "W", "D", "L", "GD", "Pts"]], "Official Standings")
    make_table(pr.reset_index()[["Power Rank", "Team", "Power Score", "Elo Rating", "Form", "GD Momentum"]], "Power Rankings")
    make_table(analytics_df[["Team", "Strength of Schedule", "Form Index", "GD Momentum", "Trend", "Projected Rank", "Tier"]], "Advanced Analytics")
    if not upcoming.empty:
        make_table(upcoming[["Week", "Date", "Time", "Match", "Favorite", "Favorite Win %", "Upset Alert", "Form Edge"]], "Upcoming Predictions")

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
def inject_css():
    st.markdown(
        f"""
        <style>
        .main .block-container {{
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }}

        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {PFC_NAVY} 0%, {PFC_DARK} 100%);
        }}

        [data-testid="stSidebar"] * {{
            color: white !important;
        }}

        /* Admin login form — override the white-on-white problem */
        [data-testid="stSidebar"] input[type="password"],
        [data-testid="stSidebar"] input[type="text"] {{
            color: {PFC_DARK} !important;
            background-color: white !important;
            border: 1px solid rgba(255,255,255,0.4) !important;
            border-radius: 6px !important;
        }}

        [data-testid="stSidebar"] input[type="password"]::placeholder,
        [data-testid="stSidebar"] input[type="text"]::placeholder {{
            color: #888 !important;
        }}

        [data-testid="stSidebar"] .stFormSubmitButton button {{
            background-color: {PFC_GOLD} !important;
            color: {PFC_DARK} !important;
            font-weight: 800 !important;
            border: none !important;
            border-radius: 8px !important;
        }}

        [data-testid="stSidebar"] .stFormSubmitButton button:hover {{
            background-color: #C9A227 !important;
            color: {PFC_DARK} !important;
        }}

        [data-testid="stSidebar"] .stRadio label {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 10px 12px;
            margin-bottom: 8px;
            width: 100%;
        }}

        [data-testid="stSidebar"] .stRadio label:hover {{
            background: rgba(255,255,255,0.14);
            border-color: rgba(255,255,255,0.35);
        }}

        .section-header {{
            font-size: 1.35rem;
            font-weight: 900;
            color: {PFC_NAVY};
            border-bottom: 3px solid {PFC_BLUE};
            padding-bottom: 6px;
            margin-bottom: 16px;
            margin-top: 8px;
        }}

        .mini-card {{
            background: white;
            border: 1px solid #DCE5FF;
            border-radius: 12px;
            padding: 12px 14px;
            box-shadow: 0 2px 10px rgba(0,0,0,.04);
            height: 100%;
        }}

        .mini-label {{
            font-size: 0.82rem;
            color: #5A6480;
            line-height: 1.25;
            margin-top: 8px;
        }}

        .rank-card {{
            background: linear-gradient(90deg, {PFC_NAVY} 0%, {PFC_BLUE} 100%);
            border-radius: 16px;
            padding: 14px 18px;
            margin: 8px 0;
            display: flex;
            align-items: center;
            gap: 14px;
            box-shadow: 0 5px 14px rgba(27,47,107,.14);
        }}

        .rank-num {{
            font-size: 2rem;
            font-weight: 900;
            color: white;
            min-width: 54px;
            text-align: center;
        }}

        .rank-team {{
            font-size: 1.2rem;
            font-weight: 800;
            color: white;
            min-width: 190px;
        }}

        .rank-score {{
            font-size: 1rem;
            font-weight: 800;
            color: {PFC_WHITE};
        }}

        .info-strip {{
            background: #EEF3FD;
            border-left: 5px solid {PFC_BLUE};
            border-radius: 10px;
            padding: 12px 14px;
            color: {PFC_DARK};
            margin-top: 12px;
        }}

        .active-division-chip {{
            background: rgba(255,255,255,0.16);
            border: 1px solid rgba(255,255,255,0.30);
            border-radius: 999px;
            padding: 8px 12px;
            font-weight: 800;
            color: white;
            text-align: center;
            margin-top: 6px;
            margin-bottom: 10px;
        }}

        .sched-row-played {{
            background: #F4F4F6;
            border-left: 4px solid {PFC_SILVER};
            border-radius: 8px;
            padding: 10px 14px;
            margin: 6px 0;
            opacity: 0.70;
        }}

        .sched-row-canceled {{
            background: #FFF0EE;
            border-left: 4px solid {PFC_RED};
            border-radius: 8px;
            padding: 10px 14px;
            margin: 6px 0;
            opacity: 0.75;
        }}

        .sched-row-bye {{
            background: #FFF6E8;
            border-left: 4px solid {PFC_ORANGE};
            border-radius: 8px;
            padding: 10px 14px;
            margin: 6px 0;
            opacity: 0.80;
        }}

        .sched-row-scheduled {{
            background: #F0FAF4;
            border-left: 4px solid {PFC_GREEN};
            border-radius: 8px;
            padding: 10px 14px;
            margin: 6px 0;
        }}

        .counts-banner {{
            background: #F3EEFF;
            border: 1px solid #C9B8F0;
            border-radius: 8px;
            padding: 10px 14px;
            margin-top: 10px;
            font-size: 0.9rem;
            color: {PFC_PURPLE};
            font-weight: 600;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# ADMIN AUTH
# ─────────────────────────────────────────────
def is_admin() -> bool:
    return st.session_state.get("admin_unlocked", False)


def render_admin_sidebar():
    st.sidebar.divider()
    if is_admin():
        st.sidebar.markdown(
            f'<div style="background:rgba(46,139,87,0.25);border:1px solid {PFC_GREEN};border-radius:10px;'
            f'padding:8px 12px;text-align:center;font-weight:700;color:white;">🔓 Admin Mode</div>',
            unsafe_allow_html=True,
        )
        if st.sidebar.button("🔒 Lock Admin", key="lock_btn", use_container_width=True):
            st.session_state["admin_unlocked"] = False
            st.rerun()
    else:
        st.sidebar.markdown(
            f'<div style="background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.20);'
            f'border-radius:10px;padding:8px 12px;text-align:center;font-weight:700;color:white;">🔒 View-Only Mode</div>',
            unsafe_allow_html=True,
        )
        with st.sidebar.form("admin_login_form", clear_on_submit=True):
            pw = st.text_input("Admin Password", type="password", label_visibility="collapsed",
                               placeholder="Enter admin password")
            login = st.form_submit_button("Unlock", use_container_width=True)
        if login:
            if pw == ADMIN_PASSWORD:
                st.session_state["admin_unlocked"] = True
                st.rerun()
            else:
                st.sidebar.error("Incorrect password.")


def require_admin(label: str = "this action"):
    if not is_admin():
        st.warning(f"🔒 Admin access required to {label}. Use the sidebar to unlock.")
        return False
    return True


# ─────────────────────────────────────────────
# COUNTS-FOR HELPER UI
# ─────────────────────────────────────────────
def counts_for_selector(key: str, default: str = "Both Teams", home_team: str = "", away_team: str = "") -> str:
    cf = st.radio(
        "Result counts for",
        COUNTS_OPTIONS,
        index=COUNTS_OPTIONS.index(default) if default in COUNTS_OPTIONS else 0,
        horizontal=True,
        key=key,
        help=(
            "Both Teams = normal game, result counts for standings of both teams.\n"
            "Home Only = only the home team gets standings credit.\n"
            "Away Only = only the away team gets standings credit.\n"
            "Neither = friendly/exhibition, no standings impact."
        ),
    )

    if cf == "Both Teams":
        st.markdown(
            f'<div class="counts-banner">✅ Normal game — result counts for <b>both</b> teams in standings.</div>',
            unsafe_allow_html=True,
        )
    elif cf == "Home Only":
        ht = home_team or "Home team"
        at = away_team or "Away team"
        st.markdown(
            f'<div class="counts-banner">⚠️ Result will count for <b>{ht}</b> only. <b>{at}</b> is the fill-in — their result does NOT affect standings.</div>',
            unsafe_allow_html=True,
        )
    elif cf == "Away Only":
        ht = home_team or "Home team"
        at = away_team or "Away team"
        st.markdown(
            f'<div class="counts-banner">⚠️ Result will count for <b>{at}</b> only. <b>{ht}</b> is the fill-in — their result does NOT affect standings.</div>',
            unsafe_allow_html=True,
        )
    elif cf == "Neither":
        st.markdown(
            f'<div class="counts-banner">🤝 Friendly / exhibition game — no standings impact for either team.</div>',
            unsafe_allow_html=True,
        )

    return cf


# ─────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────
def page_game_manager(df, division: str, teams: list[str]):
    st.markdown('<div class="section-header">📋 Game Manager</div>', unsafe_allow_html=True)

    sched_df = load_schedule_from_db(division)

    completed_map = {}
    for _, mr in df.iterrows():
        key = (str(mr["game_date"]), str(mr["home_team"]), str(mr["away_team"]))
        completed_map[key] = mr

    admin = is_admin()

    tab_schedule, tab_add, tab_edit_results = st.tabs([
        "📅 Schedule & Score Entry",
        "➕ Add New Game",
        "✏️ Edit / Delete Results",
    ])

    with tab_schedule:
        if sched_df.empty:
            st.info("No schedule loaded yet.")
        else:
            st.markdown(
                f"""
                <div class="info-strip">
                <b>Legend:</b>
                &nbsp;<span style="color:{PFC_GREEN};font-weight:700;">● Scheduled</span>
                &nbsp;&nbsp;<span style="color:{PFC_SILVER};font-weight:700;">● Played</span>
                &nbsp;&nbsp;<span style="color:{PFC_RED};font-weight:700;">● Canceled</span>
                &nbsp;&nbsp;<span style="color:{PFC_ORANGE};font-weight:700;">● Bye</span>
                &nbsp;&nbsp;<span style="color:{PFC_PURPLE};font-weight:700;">● Partial Count</span>
                {"&nbsp;&nbsp;— Click a game row to take action." if admin else "&nbsp;&nbsp;— Unlock admin in the sidebar to make changes."}
                </div>
                """,
                unsafe_allow_html=True,
            )

            col_wf, col_sf = st.columns([1, 1])
            with col_wf:
                weeks = ["All"] + sorted(sched_df["week"].unique().tolist())
                sel_week = st.selectbox("Filter by Week", weeks, key="gm_week_filter")
            with col_sf:
                sel_status = st.selectbox(
                    "Filter by Status",
                    ["All", "scheduled", "played", "canceled", "bye"],
                    key="gm_status_filter",
                )

            view_df = sched_df.copy()
            if sel_week != "All":
                view_df = view_df[view_df["week"] == int(sel_week)]
            if sel_status != "All":
                view_df = view_df[view_df["status"] == sel_status]

            if view_df.empty:
                st.info("No games match the selected filters.")
            else:
                for _, row in view_df.iterrows():
                    game_id = int(row["id"])
                    status = row["status"]
                    css_class = f"sched-row-{status}"
                    badge = status_badge(status)
                    note_str = f" — <i>{row['notes']}</i>" if row.get("notes") else ""

                    result_key = (str(row["game_date"]), str(row["home_team"]), str(row["away_team"]))
                    result_row = completed_map.get(result_key)
                    score_str = ""
                    cf_badge_str = ""
                    if result_row is not None:
                        score_str = f"&nbsp;&nbsp;<b style='color:{PFC_NAVY}'>{int(result_row['home_goals'])} – {int(result_row['away_goals'])}</b>"
                        cf = result_row.get("counts_for", "Both Teams") or "Both Teams"
                        cf_badge_str = counts_for_badge(cf)

                    st.markdown(
                        f"""
                        <div class="{css_class}">
                            <b>Wk {int(row['week'])}</b> &nbsp;·&nbsp;
                            {format_display_date(row['game_date'])} {row['time']} &nbsp;·&nbsp;
                            <b>{row['home_team']}</b> vs <b>{row['away_team']}</b> &nbsp;·&nbsp;
                            {row['location']} &nbsp; {badge}{score_str}{cf_badge_str}{note_str}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if admin:
                        with st.expander(f"⚙️ Actions — {row['home_team']} vs {row['away_team']} (Wk {int(row['week'])})", expanded=False):
                            action = st.radio(
                                "What do you want to do?",
                                ["⚽ Enter / Update Score", "🗓️ Reschedule", "🚫 Cancel", "😴 Mark as Bye", "♻️ Restore to Scheduled"],
                                key=f"action_{game_id}",
                                horizontal=True,
                            )

                            if action == "⚽ Enter / Update Score":
                                st.markdown(f"**Enter result for {row['home_team']} vs {row['away_team']}**")

                                pre_hg = int(result_row["home_goals"]) if result_row is not None else 0
                                pre_ag = int(result_row["away_goals"]) if result_row is not None else 0
                                pre_notes = str(result_row["notes"]) if result_row is not None else ""
                                pre_cf = str(result_row.get("counts_for", "Both Teams")) if result_row is not None else "Both Teams"
                                if pre_cf not in COUNTS_OPTIONS:
                                    pre_cf = "Both Teams"

                                sc1, sc2, sc3 = st.columns(3)
                                with sc1:
                                    hg = st.number_input(
                                        f"{row['home_team']} Goals",
                                        min_value=0, max_value=30, value=pre_hg, step=1,
                                        key=f"hg_{game_id}"
                                    )
                                with sc2:
                                    ag = st.number_input(
                                        f"{row['away_team']} Goals",
                                        min_value=0, max_value=30, value=pre_ag, step=1,
                                        key=f"ag_{game_id}"
                                    )
                                with sc3:
                                    match_notes = st.text_input(
                                        "Match Notes", value=pre_notes,
                                        placeholder="e.g. Rain delay",
                                        key=f"mnotes_{game_id}"
                                    )

                                st.markdown("---")
                                cf_val = counts_for_selector(
                                    key=f"cf_{game_id}",
                                    default=pre_cf,
                                    home_team=row["home_team"],
                                    away_team=row["away_team"],
                                )

                                st.markdown("---")
                                if st.button("⚽ Save Score & Mark Played", key=f"save_score_{game_id}", use_container_width=True, type="primary"):
                                    if result_row is not None:
                                        update_match(
                                            int(result_row["id"]), division,
                                            int(row["week"]), row["game_date"],
                                            row["home_team"], row["away_team"],
                                            hg, ag, match_notes, cf_val,
                                        )
                                    else:
                                        insert_match(
                                            division, int(row["week"]), row["game_date"],
                                            row["home_team"], row["away_team"],
                                            hg, ag, match_notes, cf_val,
                                        )
                                    set_game_status(game_id, "played", "")
                                    st.success(f"✅ Saved: {row['home_team']} {hg} – {ag} {row['away_team']} ({cf_val})")
                                    st.rerun()

                            elif action == "🗓️ Reschedule":
                                st.markdown("**Move this game to a new date/time/location.**")
                                with st.form(f"reschedule_form_{game_id}", clear_on_submit=False):
                                    rs1, rs2 = st.columns(2)
                                    with rs1:
                                        new_week = st.number_input("New Week", min_value=1, max_value=52, value=int(row["week"]), step=1, key=f"rswk_{game_id}")
                                        new_date = st.date_input("New Date", value=parse_to_date(row["game_date"]), format="MM/DD/YYYY", key=f"rsdt_{game_id}")
                                    with rs2:
                                        new_time = st.text_input("New Time", value=str(row["time"]), key=f"rstm_{game_id}")
                                        new_loc = st.text_input("New Location", value=str(row["location"]), key=f"rslc_{game_id}")
                                    rs_notes = st.text_input("Notes", value="", placeholder="e.g. Rescheduled due to rain", key=f"rsnotes_{game_id}")
                                    save_rs = st.form_submit_button("💾 Save Reschedule", use_container_width=True)

                                if save_rs:
                                    update_schedule_game(game_id, new_week, new_date, row["home_team"], row["away_team"], new_loc, new_time, "scheduled", rs_notes)
                                    st.success(f"Rescheduled to Week {new_week}, {format_display_date(new_date)} {new_time} @ {new_loc}")
                                    st.rerun()

                            elif action == "🚫 Cancel":
                                with st.form(f"cancel_form_{game_id}"):
                                    cancel_reason = st.text_input("Reason (optional)", placeholder="e.g. Field closed, weather", key=f"cancelreason_{game_id}")
                                    if st.form_submit_button("🚫 Confirm Cancellation", use_container_width=True):
                                        set_game_status(game_id, "canceled", cancel_reason)
                                        st.success(f"Marked as Canceled: {row['home_team']} vs {row['away_team']}")
                                        st.rerun()

                            elif action == "😴 Mark as Bye":
                                with st.form(f"bye_form_{game_id}"):
                                    bye_notes = st.text_input("Notes (optional)", placeholder="e.g. Opponent no-show", key=f"byenotes_{game_id}")
                                    if st.form_submit_button("😴 Confirm Bye", use_container_width=True):
                                        set_game_status(game_id, "bye", bye_notes)
                                        st.success(f"Marked as Bye: {row['home_team']} vs {row['away_team']}")
                                        st.rerun()

                            elif action == "♻️ Restore to Scheduled":
                                with st.form(f"restore_form_{game_id}"):
                                    if st.form_submit_button("♻️ Restore to Scheduled", use_container_width=True):
                                        set_game_status(game_id, "scheduled", "")
                                        st.success(f"Restored: {row['home_team']} vs {row['away_team']}")
                                        st.rerun()

            st.caption(f"Showing {len(view_df)} game(s).")

    with tab_add:
        if not require_admin("add games to the schedule"):
            st.stop()

        st.markdown("Add a makeup game, extra fixture, or any game not on the schedule.")

        # Use all_teams (including PSY) for game entry dropdowns so you can still log those results
        all_teams = load_division_teams(division)
        a1, a2, a3 = st.columns(3)
        with a1:
            add_week = st.number_input("Week", min_value=1, max_value=52, value=1, step=1, key="ag_week")
            add_date = st.date_input("Date", value=date.today(), format="MM/DD/YYYY", key="ag_date")
        with a2:
            add_home = st.selectbox("Home Team", all_teams, key="ag_home")
            add_time = st.text_input("Time", value="9:00 AM", placeholder="e.g. 10:30 AM", key="ag_time")
        with a3:
            add_away = st.selectbox("Away Team", all_teams, key="ag_away")
            add_location = st.text_input("Location", value="", placeholder="e.g. Field 4", key="ag_loc")

        add_notes = st.text_input("Notes (optional)", placeholder="e.g. Makeup game from Week 3 cancellation", key="ag_notes")

        if st.button("➕ Add Game to Schedule", key="add_game_btn", use_container_width=True, type="primary"):
            if add_home == add_away:
                st.error("A team cannot play itself.")
            else:
                insert_schedule_game(division, add_week, add_date, add_home, add_away, add_location, add_time, add_notes)
                st.success(f"Added: {add_home} vs {add_away} — Week {add_week}, {format_display_date(add_date)} {add_time}")
                st.rerun()

    with tab_edit_results:
        if not require_admin("edit or delete match results"):
            st.stop()

        if df.empty:
            st.info("No results logged yet.")
        else:
            st.markdown("Edit or delete a previously logged match result.")

            # Use all_teams for editing dropdowns
            all_teams = load_division_teams(division)
            manage_df = prep_match_display(df.copy())
            manage_df["Score"] = manage_df["home_goals"].astype(str) + "–" + manage_df["away_goals"].astype(str)
            display_list = manage_df[["id", "week", "game_date", "home_team", "Score", "away_team", "counts_for", "notes"]].copy()
            display_list.columns = ["ID", "Week", "Date", "Home", "Score", "Away", "Counts For", "Notes"]
            st.dataframe(display_list, use_container_width=True, hide_index=True)

            selected_id = st.selectbox(
                "Select a result to edit or delete",
                manage_df["id"].tolist(),
                format_func=lambda x: (
                    f"Wk {int(manage_df.loc[manage_df['id'] == x, 'week'].iloc[0])} | "
                    f"{manage_df.loc[manage_df['id'] == x, 'game_date'].iloc[0]} | "
                    f"{manage_df.loc[manage_df['id'] == x, 'home_team'].iloc[0]} "
                    f"{int(manage_df.loc[manage_df['id'] == x, 'home_goals'].iloc[0])}-"
                    f"{int(manage_df.loc[manage_df['id'] == x, 'away_goals'].iloc[0])} "
                    f"{manage_df.loc[manage_df['id'] == x, 'away_team'].iloc[0]}"
                ),
                key="edit_result_select",
            )

            sel = manage_df[manage_df["id"] == selected_id].iloc[0]
            pre_cf = str(sel.get("counts_for", "Both Teams"))
            if pre_cf not in COUNTS_OPTIONS:
                pre_cf = "Both Teams"

            ec1, ec2, ec3 = st.columns(3)
            with ec1:
                e_week = st.number_input("Week", min_value=1, max_value=52, value=int(sel["week"]), step=1, key="edit_week")
                e_date = st.date_input("Date", value=parse_to_date(sel["game_date"]), format="MM/DD/YYYY", key="edit_date")
            with ec2:
                e_home = st.selectbox("Home Team", all_teams, index=all_teams.index(sel["home_team"]) if sel["home_team"] in all_teams else 0, key="edit_home")
                e_hg = st.number_input("Home Goals", min_value=0, max_value=30, value=int(sel["home_goals"]), step=1, key="edit_hg")
            with ec3:
                e_away = st.selectbox("Away Team", all_teams, index=all_teams.index(sel["away_team"]) if sel["away_team"] in all_teams else 0, key="edit_away")
                e_ag = st.number_input("Away Goals", min_value=0, max_value=30, value=int(sel["away_goals"]), step=1, key="edit_ag")

            e_notes = st.text_input("Notes", value=str(sel["notes"]), key="edit_notes")

            st.markdown("---")
            e_cf = counts_for_selector(
                key="edit_cf",
                default=pre_cf,
                home_team=str(sel["home_team"]),
                away_team=str(sel["away_team"]),
            )

            st.markdown("---")
            col_sv, col_del = st.columns(2)

            if col_sv.button("💾 Save Changes", key="save_edit_btn", use_container_width=True, type="primary"):
                if e_home == e_away:
                    st.error("A team cannot play itself.")
                elif match_exists(division, e_week, e_date, e_home, e_away, e_hg, e_ag, exclude_id=int(sel["id"])):
                    st.warning("That exact result already exists.")
                else:
                    update_match(int(sel["id"]), division, e_week, e_date, e_home, e_away, e_hg, e_ag, e_notes, e_cf)
                    st.success("Result updated.")
                    st.rerun()

            if col_del.button("🗑️ Delete Result", key="delete_edit_btn", use_container_width=True):
                delete_match(int(sel["id"]))
                st.success("Result deleted.")
                st.rerun()


def page_teams(division: str, teams: list[str]):
    st.markdown('<div class="section-header">👥 Team Management</div>', unsafe_allow_html=True)
    # Use all teams (including PSY) for team management
    all_teams = load_division_teams(division)

    if not require_admin("add or edit teams"):
        st.markdown("#### Current Teams")
        pfc_teams = get_pfc_teams(division, all_teams)
        non_pfc = [t for t in all_teams if t not in pfc_teams]
        st.markdown("**PFC Teams (included in rankings)**")
        st.dataframe(pd.DataFrame({"Team": sorted(pfc_teams)}), width="stretch", hide_index=True)
        if non_pfc:
            st.markdown("**Opponents / Non-PFC (schedule only)**")
            st.dataframe(pd.DataFrame({"Team": sorted(non_pfc)}), width="stretch", hide_index=True)
        return

    add_tab, edit_tab, delete_tab = st.tabs(["Add Team", "Edit Team Name", "Delete Team"])

    with add_tab:
        with st.form(f"add_team_form_{division}", clear_on_submit=True):
            new_team = st.text_input("New Team Name")
            add_submitted = st.form_submit_button("➕ Add Team", width="stretch")
        if add_submitted:
            new_team = new_team.strip()
            if not new_team:
                st.error("Enter a team name.")
            elif new_team in all_teams:
                st.warning("That team already exists.")
            else:
                add_team(division, new_team)
                st.success(f"Added {new_team} to {division}.")
                st.rerun()

    with edit_tab:
        if not all_teams:
            st.info("No teams found.")
        else:
            with st.form(f"rename_team_form_{division}"):
                old_team = st.selectbox("Current Team Name", all_teams, key=f"old_team_{division}")
                new_team_name = st.text_input("New Team Name")
                rename_submitted = st.form_submit_button("✏️ Save Team Name Change", width="stretch")
            if rename_submitted:
                new_team_name = new_team_name.strip()
                if not new_team_name:
                    st.error("Enter a new team name.")
                elif new_team_name in all_teams and new_team_name != old_team:
                    st.warning("That new team name already exists.")
                else:
                    rename_team(division, old_team, new_team_name)
                    st.success(f"Renamed {old_team} to {new_team_name}.")
                    st.rerun()

    with delete_tab:
        if not all_teams:
            st.info("No teams found.")
        else:
            with st.form(f"delete_team_form_{division}"):
                team_to_delete = st.selectbox("Team to Delete", all_teams, key=f"delete_team_{division}")
                delete_submit = st.form_submit_button("🗑️ Delete Team", width="stretch")
            if delete_submit:
                if can_delete_team(division, team_to_delete):
                    delete_team(division, team_to_delete)
                    st.success(f"Deleted {team_to_delete}.")
                    st.rerun()
                else:
                    st.error("This team already has matches logged. Delete the matches first or rename instead.")

    st.markdown("#### Current Teams")
    pfc_teams = get_pfc_teams(division, all_teams)
    non_pfc = [t for t in all_teams if t not in pfc_teams]
    st.markdown("**PFC Teams (included in rankings)**")
    st.dataframe(pd.DataFrame({"Team": sorted(pfc_teams)}), width="stretch", hide_index=True)
    if non_pfc:
        st.markdown("**Opponents / Non-PFC (schedule only)**")
        st.dataframe(pd.DataFrame({"Team": sorted(non_pfc)}), width="stretch", hide_index=True)


def page_match_history(df, teams: list[str]):
    st.markdown('<div class="section-header">📋 Match History</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No matches recorded yet.")
        return

    # Use all teams in history (PSY games show in history for reference)
    all_teams_in_data = sorted(set(df["home_team"].tolist() + df["away_team"].tolist()))

    col1, col2 = st.columns(2)
    with col1:
        weeks = ["All"] + sorted(df["week"].unique().tolist())
        sel_week = st.selectbox("Filter by Week", weeks)
    with col2:
        team_list = ["All"] + all_teams_in_data
        sel_team = st.selectbox("Filter by Team", team_list)

    filtered = df.copy()
    if sel_week != "All":
        filtered = filtered[filtered["week"] == sel_week]
    if sel_team != "All":
        filtered = filtered[(filtered["home_team"] == sel_team) | (filtered["away_team"] == sel_team)]

    display = prep_match_display(filtered.copy())
    display["Score"] = display["home_goals"].astype(str) + " – " + display["away_goals"].astype(str)
    display = display[["week", "game_date", "home_team", "Score", "away_team", "counts_for", "notes"]]
    display.columns = ["Week", "Date", "Home", "Score", "Away", "Counts For", "Notes"]

    st.dataframe(display.reset_index(drop=True), width="stretch", hide_index=True)
    st.caption(f"Showing {len(display)} match(es)")

    partial = display[display["Counts For"] != "Both Teams"]
    if not partial.empty:
        st.markdown(
            f'<div class="info-strip">⚠️ <b>{len(partial)} game(s)</b> in this view have partial standings impact '
            f'(Home Only, Away Only, or Friendly). These are excluded from or partially applied to standings calculations.</div>',
            unsafe_allow_html=True,
        )


def page_standings(df, teams: list[str]):
    st.markdown('<div class="section-header">🏆 Official Standings</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="info-strip">
        <b>Official rules:</b> Win = 3 points, Draw = 1 point, Loss = 0 points.
        Goal differential is capped at <b>±4 per match</b> for standings only.
        Games marked "Home Only", "Away Only", or "Friendly" apply standings credit only to the applicable team(s).
        <b>PSY T1 and PSY T2 are not ranked</b> — points earned against them count toward PFC team totals.
        </div>
        """,
        unsafe_allow_html=True,
    )

    standings = compute_standings(df, teams).reset_index()
    movement = compute_standings_movement(df, teams)

    standings["Move"] = standings["Team"].apply(lambda t: movement_arrow(movement.get(t, 0)))
    standings = standings[["Rank", "Team", "Move", "GP", "W", "D", "L", "GF", "GA", "GD", "Pts", "PPG"]]
    st.dataframe(standings, width="stretch", hide_index=True)


def page_power_rankings(df, teams: list[str]):
    st.markdown('<div class="section-header">⚡ Power Rankings</div>', unsafe_allow_html=True)

    pr, match_analytics, _ = compute_power_package(df, teams)
    movement = compute_power_movement(df, teams)

    display = pr.reset_index().copy()
    display["Move"] = display["Team"].apply(lambda t: movement_arrow(movement.get(t, 0)))
    display = display[["Power Rank", "Team", "Move", "Power Score", "Elo Rating", "Form", "Form Index", "GD Momentum", "Strength of Schedule"]]
    st.dataframe(display, width="stretch", hide_index=True)

    st.markdown("#### Visual Power Rankings")
    for _, row in pr.reset_index().iterrows():
        team = row["Team"]
        delta = movement.get(team, 0)
        arrow = movement_arrow(delta)
        arrow_color = movement_color(delta)
        form_html = form_badge_html(row["Form"])
        bar_pct = max(8, min(100, (row["Power Score"] - 1450) / 180 * 100))

        st.markdown(
            f"""
            <div class="rank-card">
                <div class="rank-num">{int(row["Power Rank"])}</div>
                <div class="rank-team">{team}</div>
                <div style="flex:2;background:#D8E1F6;border-radius:999px;height:14px;overflow:hidden;">
                    <div style="width:{bar_pct:.1f}%;height:100%;background:linear-gradient(90deg,{PFC_LIGHT_BLUE},{PFC_WHITE});"></div>
                </div>
                <div class="rank-score">{row["Power Score"]}</div>
                <div style="min-width:90px;text-align:center;">{form_html}</div>
                <div style="min-width:56px;text-align:right;font-weight:900;color:{arrow_color};">{arrow}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="info-strip">
        <b>How power rankings work:</b> PFC teams only — PSY T1 and PSY T2 are excluded from rankings.
        Rankings use <b>Elo rating</b> (which accounts for games against all opponents including PSY teams),
        <b>strength of schedule</b>, <b>weighted last-5 form index</b>,
        <b>goal differential momentum</b>, and <b>upset impact</b>.
        Elo always updates regardless of "Counts For" setting — because the game was played.
        Form and standings stats respect the "Counts For" setting.
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_upcoming_matches(df, division: str, teams: list[str]):
    st.markdown('<div class="section-header">🔮 Upcoming Match Predictions</div>', unsafe_allow_html=True)

    upcoming = compute_upcoming_predictions(df, division, teams)
    if upcoming.empty:
        st.info("No upcoming scheduled matches found.")
        return

    game_of_week = upcoming.sort_values(["Game Score", "Favorite Win %"], ascending=[False, True]).iloc[0]
    st.markdown(
        f"""
        <div class="info-strip">
        <b>Next Scheduled Week:</b> Week {int(upcoming["Week"].min())}<br>
        <b>Game of the Week:</b> {game_of_week["Match"]} on {game_of_week["Date"]} at {game_of_week["Time"]}. 
        Favorite: <b>{game_of_week["Favorite"]}</b> ({game_of_week["Favorite Win %"]}%).
        Upset Alert: <b>{game_of_week["Upset Alert"]}</b>.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.dataframe(
        upcoming[["Week", "Date", "Time", "Match", "Favorite", "Favorite Win %", "Upset Alert", "Form Edge", "Location"]],
        width="stretch",
        hide_index=True,
    )


def page_dashboard(df, division: str, teams: list[str]):
    st.markdown('<div class="section-header">📊 League Dashboard</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No match data yet.")
        return

    standings = compute_standings(df, teams)
    pr, match_analytics, team_analytics = compute_power_package(df, teams)
    power_movement = compute_power_movement(df, teams)
    standings_movement = compute_standings_movement(df, teams)
    upcoming = compute_upcoming_predictions(df, division, teams)

    total_goals = int(df["home_goals"].sum() + df["away_goals"].sum())
    avg_goals = round(total_goals / max(len(df), 1), 1)
    current_week = int(df["week"].max())
    partial_count = len(df[df["counts_for"] != "Both Teams"]) if "counts_for" in df.columns else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Goals", total_goals)
    m2.metric("Avg Goals / Match", avg_goals)
    m3.metric("Matches Played", len(df))
    m4.metric("Current Week", current_week)
    m5.metric("Partial-Count Games", partial_count)

    st.divider()

    left, right = st.columns([1.05, 0.95])

    with left:
        st.markdown("#### Official Standings")
        standings_display = standings.reset_index().copy()
        standings_display["Move"] = standings_display["Team"].apply(lambda t: movement_arrow(standings_movement.get(t, 0)))
        standings_display = standings_display[["Rank", "Team", "Move", "GP", "W", "D", "L", "GD", "Pts"]]
        st.dataframe(standings_display, width="stretch", hide_index=True)

    with right:
        st.markdown("#### Power Rankings")
        pr_display = pr.reset_index().copy()
        pr_display["Move"] = pr_display["Team"].apply(lambda t: movement_arrow(power_movement.get(t, 0)))
        pr_display = pr_display[["Power Rank", "Team", "Move", "Power Score", "Elo Rating", "Form", "GD Momentum"]]
        st.dataframe(pr_display, width="stretch", hide_index=True)

    st.divider()

    # ── Advanced Analytics Spotlight ────────────────────────────────────
    st.markdown("#### Advanced Analytics Spotlight")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    best_attack = team_analytics.sort_values("GF/Game", ascending=False).iloc[0]
    best_defense = team_analytics.sort_values("GA/Game", ascending=True).iloc[0]
    toughest_sched = team_analytics.sort_values("Strength of Schedule", ascending=False).iloc[0]
    easiest_sched = team_analytics.sort_values("Strength of Schedule", ascending=True).iloc[0]
    hottest_form = team_analytics.sort_values("Form Index", ascending=False).iloc[0]
    best_momentum = team_analytics.sort_values("GD Momentum", ascending=False).iloc[0]

    for col, label, team_row, stat, desc in [
        (c1, "Best Attack", best_attack, f'{best_attack["GF/Game"]} goals/game', "Highest goals scored per game."),
        (c2, "Best Defense", best_defense, f'{best_defense["GA/Game"]} allowed/game', "Fewest goals allowed per game."),
        (c3, "Toughest Schedule", toughest_sched, f'SOS {toughest_sched["Strength of Schedule"]}', "Highest avg opponent Elo faced."),
        (c4, "Easiest Schedule", easiest_sched, f'SOS {easiest_sched["Strength of Schedule"]}', "Lowest avg opponent Elo faced."),
        (c5, "Best Form", hottest_form, f'Index {hottest_form["Form Index"]}', "Weighted last-5 performance."),
        (c6, "Best Momentum", best_momentum, f'{best_momentum["GD Momentum"]}', "Recent scoring margin trend."),
    ]:
        col.markdown(
            f'<div class="mini-card"><b>{label}</b><br><span style="font-size:1.1rem;font-weight:900;color:{PFC_NAVY};">{team_row["Team"]}</span><br>{stat}<div class="mini-label">{desc}</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    st.markdown("#### Next Week Match Predictions")
    if not upcoming.empty:
        st.dataframe(
            upcoming[["Week", "Date", "Time", "Match", "Favorite", "Favorite Win %", "Upset Alert", "Form Edge"]],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No upcoming matches available.")

    st.divider()

    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.markdown("#### Points by Team")
        pts_df = standings.reset_index()[["Team", "Pts"]].sort_values("Pts", ascending=False)
        fig_pts = px.bar(pts_df, x="Team", y="Pts", text="Pts", color="Pts", color_continuous_scale=["#C9D7FA", PFC_NAVY])
        fig_pts.update_traces(textposition="outside")
        fig_pts.update_layout(paper_bgcolor=PFC_WHITE, plot_bgcolor=PFC_WHITE, font_color=PFC_DARK, showlegend=False, coloraxis_showscale=False, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_pts, width="stretch")

    with chart_right:
        st.markdown("#### Goals For vs Goals Against")
        gf_ga = standings.reset_index()[["Team", "GF", "GA"]].sort_values("GF", ascending=False)
        fig_gfga = go.Figure()
        fig_gfga.add_trace(go.Bar(name="Goals For", x=gf_ga["Team"], y=gf_ga["GF"], marker_color=PFC_BLUE))
        fig_gfga.add_trace(go.Bar(name="Goals Against", x=gf_ga["Team"], y=gf_ga["GA"], marker_color=PFC_SILVER))
        fig_gfga.update_layout(barmode="group", paper_bgcolor=PFC_WHITE, plot_bgcolor=PFC_WHITE, font_color=PFC_DARK, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_gfga, width="stretch")

    st.divider()

    lower_left, lower_right = st.columns(2)

    with lower_left:
        st.markdown("#### Recent Results")
        recent = prep_match_display(df.sort_values(["week", "game_date", "id"], ascending=False).head(6).copy())
        for _, row in recent.iterrows():
            cf = row.get("counts_for", "Both Teams") or "Both Teams"
            cf_note = f" *({cf})*" if cf != "Both Teams" else ""
            st.markdown(
                f"**Wk {int(row['week'])}** · {row['game_date']} · "
                f"{row['home_team']} **{int(row['home_goals'])}-{int(row['away_goals'])}** {row['away_team']}"
                + cf_note
                + (f"  —  *{row['notes']}*" if row["notes"] else "")
            )

        st.markdown("#### Match Impact View")
        impact = match_analytics.copy().sort_values(["Total Impact", "Upset Probability"], ascending=False).head(5)
        impact["Date"] = impact["Date"].apply(format_display_date)
        impact["Match"] = impact["Home"] + " " + impact["Score"] + " " + impact["Away"]
        st.dataframe(
            impact[["Week", "Date", "Match", "Counts For", "Expected Winner", "Winner", "Upset Probability", "Total Impact"]],
            width="stretch",
            hide_index=True,
        )

    with lower_right:
        st.markdown("#### Projected Table Insights")
        proj = team_analytics.sort_values(["Projected Rank"]).copy()
        st.dataframe(
            proj[["Projected Rank", "Team", "Tier", "Trend", "Strength of Schedule", "Form Index", "GD Momentum", "Projected Score"]]
            .rename(columns={"Projected Rank": "Proj Rank", "Strength of Schedule": "SOS"}),
            width="stretch",
            hide_index=True,
        )

        riser = max(power_movement.items(), key=lambda x: x[1])
        faller = min(power_movement.items(), key=lambda x: x[1])
        c1, c2 = st.columns(2)
        if riser[1] > 0:
            c1.success(f"Biggest Riser: {riser[0]} (+{riser[1]})")
        else:
            c1.info("Biggest Riser: No movement yet")
        if faller[1] < 0:
            c2.error(f"Biggest Faller: {faller[0]} ({faller[1]})")
        else:
            c2.info("Biggest Faller: No movement yet")

    # ── Playoff Picture ───────────────────────────────────────────────────
    if division == "U15 Boys":
        st.divider()
        render_playoff_picture(df, division, teams)

    st.markdown(
        f"""
        <div class="info-strip">
        <b>Analytics notes:</b> Official standings use capped goal differential.
        PSY T1 and PSY T2 appear in match history and schedule but are excluded from all rankings and analytics tables.
        Points earned against PSY opponents count toward PFC team standings totals.
        Games with a partial "Counts For" setting apply credit only to the applicable team(s).
        Power rankings Elo always updates regardless of "Counts For" — because the game was played.
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_notes(division: str):
    st.markdown('<div class="section-header">📣 League Notes & Announcements</div>', unsafe_allow_html=True)

    if is_admin():
        with st.form(f"note_form_{division}", clear_on_submit=True):
            note_text = st.text_area("Add a new note or announcement", height=120, placeholder="e.g. Next games moved to Saturday...")
            submitted = st.form_submit_button("📌 Post Note", width="stretch")
        if submitted and note_text.strip():
            insert_note(division, note_text.strip())
            st.success("Note posted.")
            st.rerun()
    else:
        st.info("🔒 Unlock admin to post or delete notes.")

    notes_df = load_notes(division)
    if notes_df.empty:
        st.info("No notes yet.")
    else:
        for _, row in notes_df.iterrows():
            created_fmt = format_display_date(str(row["created"]).split(" ")[0]) + " " + str(row["created"]).split(" ")[1] if " " in str(row["created"]) else row["created"]
            with st.expander(f"📌 {created_fmt}", expanded=True):
                st.write(row["note_text"])
                if is_admin() and st.button("🗑️ Delete", key=f"del_note_{row['id']}"):
                    delete_note(row["id"])
                    st.rerun()


def page_export(df, division: str, teams: list[str]):
    st.markdown('<div class="section-header">📥 Export Center</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No data to export yet.")
        return

    standings = compute_standings(df, teams)
    pr, _, team_analytics = compute_power_package(df, teams)
    movement = compute_power_movement(df, teams)

    history_export = prep_match_display(df.copy())
    history_export["Score"] = history_export["home_goals"].astype(str) + " – " + history_export["away_goals"].astype(str)
    history_export = history_export[["week", "game_date", "home_team", "Score", "away_team", "counts_for", "notes"]]
    history_export.columns = ["Week", "Date", "Home", "Score", "Away", "Counts For", "Notes"]

    pdf_bytes = make_league_summary_pdf(division, standings, pr, history_export, team_analytics)
    png_bytes = make_power_rankings_png(pr, movement, division)
    dashboard_pdf = make_dashboard_pdf(division, df, teams)

    sched_export = load_schedule_from_db(division).copy()
    if not sched_export.empty:
        sched_export["game_date"] = sched_export["game_date"].apply(format_display_date)
        sched_export = sched_export[["week", "game_date", "time", "home_team", "away_team", "location", "status", "notes"]]
        sched_export.columns = ["Week", "Date", "Time", "Home", "Away", "Location", "Status", "Notes"]

    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.download_button("📄 League Summary PDF", data=pdf_bytes,
            file_name=f"{division.lower().replace(' ', '_')}_summary_{datetime.now().strftime('%m%d%Y')}.pdf",
            mime="application/pdf", width="stretch")
    with col2:
        st.download_button("📄 Dashboard PDF", data=dashboard_pdf,
            file_name=f"{division.lower().replace(' ', '_')}_dashboard_{datetime.now().strftime('%m%d%Y')}.pdf",
            mime="application/pdf", width="stretch")
    with col3:
        st.download_button("🖼️ Power Rankings PNG", data=png_bytes,
            file_name=f"{division.lower().replace(' ', '_')}_power_rankings_{datetime.now().strftime('%m%d%Y')}.png",
            mime="image/png", width="stretch")
    with col4:
        st.download_button("📋 Standings CSV", data=df_to_csv_bytes(standings.reset_index()),
            file_name=f"{division.lower().replace(' ', '_')}_standings.csv", mime="text/csv", width="stretch")
    with col5:
        st.download_button("📅 Match History CSV", data=df_to_csv_bytes(history_export),
            file_name=f"{division.lower().replace(' ', '_')}_match_history.csv", mime="text/csv", width="stretch")
    with col6:
        if not sched_export.empty:
            st.download_button("🗓️ Schedule CSV", data=df_to_csv_bytes(sched_export),
                file_name=f"{division.lower().replace(' ', '_')}_schedule_{datetime.now().strftime('%m%d%Y')}.csv",
                mime="text/csv", width="stretch")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    init_db()
    inject_css()

    st.sidebar.title("Pensacola FC")
    st.sidebar.markdown("**Division**")
    selected_division = st.sidebar.radio("Division", DIVISIONS, index=0, label_visibility="collapsed")
    st.sidebar.markdown(f'<div class="active-division-chip">Active: {selected_division}</div>', unsafe_allow_html=True)

    # Load ALL teams (for schedule/game entry), then filter to PFC-only for analytics
    all_teams = load_division_teams(selected_division)
    pfc_teams = get_pfc_teams(selected_division, all_teams)
    df = load_matches(selected_division)

    render_header(selected_division)

    logo_path = find_logo_path()
    if logo_path:
        st.sidebar.image(logo_path, width=140)
    else:
        st.sidebar.markdown("## ⚽")

    st.sidebar.divider()
    st.sidebar.title("League Navigation")

    page = st.sidebar.radio(
        "Navigate",
        [
            "📊 Dashboard",
            "📋 Game Manager",
            "👥 Teams",
            "📋 Match History",
            "🏆 Standings",
            "⚡ Power Rankings",
            "🔮 Upcoming Matches",
            "📣 Notes",
            "📥 Export",
        ],
        label_visibility="collapsed",
    )

    if not df.empty:
        st.sidebar.divider()
        st.sidebar.markdown("**League Summary**")
        st.sidebar.caption(f"Division: **{selected_division}**")
        st.sidebar.caption(f"PFC Teams: **{len(pfc_teams)}**")
        st.sidebar.caption(f"Matches: **{len(df)}**")
        st.sidebar.caption(f"Weeks Logged: **{int(df['week'].max())}**")
        total_goals = int(df["home_goals"].sum() + df["away_goals"].sum())
        st.sidebar.caption(f"Goals Scored: **{total_goals}**")
        st.sidebar.caption(f"Data Saved In: **{DB_PATH}**")

    st.sidebar.divider()
    st.sidebar.caption("Built for youth soccer league admins.")

    render_admin_sidebar()

    # All analytics pages receive pfc_teams — PSY teams excluded from rankings
    if page == "📊 Dashboard":
        page_dashboard(df, selected_division, pfc_teams)
    elif page == "📋 Game Manager":
        page_game_manager(df, selected_division, all_teams)
    elif page == "👥 Teams":
        page_teams(selected_division, pfc_teams)
    elif page == "📋 Match History":
        page_match_history(df, pfc_teams)
    elif page == "🏆 Standings":
        page_standings(df, pfc_teams)
    elif page == "⚡ Power Rankings":
        page_power_rankings(df, pfc_teams)
    elif page == "🔮 Upcoming Matches":
        page_upcoming_predictions(df, selected_division, pfc_teams)
    elif page == "📣 Notes":
        page_notes(selected_division)
    elif page == "📥 Export":
        page_export(df, selected_division, pfc_teams)


if __name__ == "__main__":
    main()
