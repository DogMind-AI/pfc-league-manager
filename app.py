"""
Youth Soccer League Manager
A complete Streamlit application for managing league standings,
power rankings, match history, advanced analytics, and exports.
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

# Upload your logo into Replit root as one of these filenames if you want it shown in the app/exports
LOGO_CANDIDATES = ["pfc_logo.png", "logo.png", "pensacola_fc_logo.png"]

# Pensacola FC style palette
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

TEAMS = [
    "Cobras",
    "Athletico",
    "Vipers",
    "PSY T1",
    "Beavers",
    "PSYT2",
    "Los Locos",
    "Pelicans",
]

WEEK1_RESULTS = [
    (1, "2025-01-01", "Cobras", "Athletico", 3, 2, "Week 1 opener"),
    (1, "2025-01-01", "Vipers", "PSY T1", 4, 0, ""),
    (1, "2025-01-01", "Beavers", "PSYT2", 3, 3, ""),
    (1, "2025-01-01", "Los Locos", "Pelicans", 7, 2, ""),
]

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


def render_header():
    logo_b64 = get_logo_base64()
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
                        U15 Boys Division Analytics Hub
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
                        U15 Boys Division Analytics Hub
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ─────────────────────────────────────────────
# DATABASE LAYER
# ─────────────────────────────────────────────

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            week       INTEGER NOT NULL,
            game_date  TEXT NOT NULL,
            home_team  TEXT NOT NULL,
            away_team  TEXT NOT NULL,
            home_goals INTEGER NOT NULL,
            away_goals INTEGER NOT NULL,
            notes      TEXT DEFAULT ''
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS league_notes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            created   TEXT NOT NULL,
            note_text TEXT NOT NULL
        )
    """)

    conn.commit()

    c.execute("SELECT COUNT(*) FROM matches")
    if c.fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO matches (week, game_date, home_team, away_team, home_goals, away_goals, notes) VALUES (?,?,?,?,?,?,?)",
            WEEK1_RESULTS
        )
        conn.commit()

    conn.close()


def load_matches() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM matches ORDER BY week, game_date, id", conn)
    conn.close()
    if not df.empty:
        df["game_date"] = df["game_date"].astype(str)
    return df


def match_exists(week, game_date, home, away, hg, ag, exclude_id=None):
    conn = get_conn()
    query = """
        SELECT COUNT(*) FROM matches
        WHERE week=? AND game_date=? AND home_team=? AND away_team=? AND home_goals=? AND away_goals=?
    """
    params = [int(week), to_iso_date(game_date), home, away, int(hg), int(ag)]
    if exclude_id is not None:
        query += " AND id <> ?"
        params.append(int(exclude_id))
    count = conn.execute(query, params).fetchone()[0]
    conn.close()
    return count > 0


def insert_match(week, game_date, home, away, hg, ag, notes):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO matches (week, game_date, home_team, away_team, home_goals, away_goals, notes)
        VALUES (?,?,?,?,?,?,?)
        """,
        (int(week), to_iso_date(game_date), home, away, int(hg), int(ag), notes.strip())
    )
    conn.commit()
    conn.close()


def update_match(match_id, week, game_date, home, away, hg, ag, notes):
    conn = get_conn()
    conn.execute(
        """
        UPDATE matches
        SET week=?, game_date=?, home_team=?, away_team=?, home_goals=?, away_goals=?, notes=?
        WHERE id=?
        """,
        (int(week), to_iso_date(game_date), home, away, int(hg), int(ag), notes.strip(), int(match_id))
    )
    conn.commit()
    conn.close()


def delete_match(match_id):
    conn = get_conn()
    conn.execute("DELETE FROM matches WHERE id=?", (int(match_id),))
    conn.commit()
    conn.close()


def load_notes() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM league_notes ORDER BY id DESC", conn)
    conn.close()
    return df


def insert_note(text):
    conn = get_conn()
    conn.execute(
        "INSERT INTO league_notes (created, note_text) VALUES (?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), text)
    )
    conn.commit()
    conn.close()


def delete_note(note_id):
    conn = get_conn()
    conn.execute("DELETE FROM league_notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# STANDINGS ENGINE
# ─────────────────────────────────────────────

def compute_standings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Official standings:
    - Win = 3
    - Draw = 1
    - Loss = 0
    - GD capped at ±4 per match
    """
    records = {
        t: dict(GP=0, W=0, D=0, L=0, GF=0, GA=0, GD_capped=0, Pts=0)
        for t in TEAMS
    }

    for _, row in df.iterrows():
        h, a = row["home_team"], row["away_team"]
        hg, ag = int(row["home_goals"]), int(row["away_goals"])

        raw_gd = hg - ag
        capped = int(np.clip(raw_gd, -4, 4))

        records[h]["GP"] += 1
        records[a]["GP"] += 1

        records[h]["GF"] += hg
        records[h]["GA"] += ag
        records[a]["GF"] += ag
        records[a]["GA"] += hg

        records[h]["GD_capped"] += capped
        records[a]["GD_capped"] -= capped

        if hg > ag:
            records[h]["W"] += 1
            records[h]["Pts"] += 3
            records[a]["L"] += 1
        elif hg < ag:
            records[a]["W"] += 1
            records[a]["Pts"] += 3
            records[h]["L"] += 1
        else:
            records[h]["D"] += 1
            records[a]["D"] += 1
            records[h]["Pts"] += 1
            records[a]["Pts"] += 1

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
    standings = standings.sort_values(
        ["Pts", "GD", "GF", "Team"],
        ascending=[False, False, False, True]
    ).reset_index(drop=True)
    standings.index += 1
    standings.index.name = "Rank"
    return standings


def compute_standings_movement(df: pd.DataFrame) -> dict:
    if df.empty:
        return {t: 0 for t in TEAMS}

    max_week = int(df["week"].max())
    prev_df = df[df["week"] < max_week]

    curr = compute_standings(df).reset_index()
    curr_ranks = {r["Team"]: int(r["Rank"]) for _, r in curr.iterrows()}

    if prev_df.empty:
        return {t: 0 for t in TEAMS}

    prev = compute_standings(prev_df).reset_index()
    prev_ranks = {r["Team"]: int(r["Rank"]) for _, r in prev.iterrows()}

    return {team: prev_ranks.get(team, len(TEAMS)) - curr_ranks.get(team, len(TEAMS)) for team in TEAMS}

# ─────────────────────────────────────────────
# POWER / ANALYTICS ENGINE
# ─────────────────────────────────────────────

def normalize_series(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    min_v = s.min()
    max_v = s.max()
    if np.isclose(min_v, max_v):
        return pd.Series([50.0] * len(s), index=s.index)
    return (s - min_v) / (max_v - min_v) * 100


def compute_power_package(df: pd.DataFrame):
    """
    Returns:
    - power_rankings_df
    - match_analytics_df
    - team_analytics_df
    """
    elo = {t: 1500.0 for t in TEAMS}
    form_results = {t: [] for t in TEAMS}
    team_goal_diffs = {t: [] for t in TEAMS}
    team_match_points = {t: [] for t in TEAMS}
    opps = {t: [] for t in TEAMS}

    match_logs = []

    sorted_df = df.sort_values(["week", "game_date", "id"]).reset_index(drop=True)
    n_matches = len(sorted_df)

    for idx, row in sorted_df.iterrows():
        h, a = row["home_team"], row["away_team"]
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        match_date = row["game_date"]

        pre_h = elo[h]
        pre_a = elo[a]

        recency_w = 1.0 + 0.06 * (idx / max(n_matches - 1, 1))
        exp_h = 1 / (1 + 10 ** ((pre_a - pre_h) / 400))
        exp_a = 1 - exp_h

        if hg > ag:
            act_h, act_a = 1.0, 0.0
            result_h, result_a = 3, 0
            winner = h
        elif hg < ag:
            act_h, act_a = 0.0, 1.0
            result_h, result_a = 0, 3
            winner = a
        else:
            act_h, act_a = 0.5, 0.5
            result_h, result_a = 1, 1
            winner = "Draw"

        form_results[h].append(result_h)
        form_results[a].append(result_a)
        team_match_points[h].append(result_h)
        team_match_points[a].append(result_a)

        home_raw_gd = hg - ag
        away_raw_gd = ag - hg
        team_goal_diffs[h].append(home_raw_gd)
        team_goal_diffs[a].append(away_raw_gd)

        goal_diff = abs(hg - ag)
        mov_mult = 1.0 + 0.10 * min(goal_diff, 8)

        upset_score = abs(act_h - exp_h)
        K_h = 32 * recency_w * mov_mult * (1 + upset_score)
        K_a = 32 * recency_w * mov_mult * (1 + upset_score)

        delta_h = K_h * (act_h - exp_h)
        delta_a = K_a * (act_a - exp_a)

        elo[h] += delta_h
        elo[a] += delta_a

        underdog = h if pre_h < pre_a else (a if pre_a < pre_h else "Even")
        upset_flag = False
        if winner != "Draw" and underdog != "Even" and winner == underdog:
            upset_flag = True
        if winner == "Draw" and abs(exp_h - 0.5) > 0.15:
            upset_flag = True

        opps[h].append(a)
        opps[a].append(h)

        match_logs.append({
            "Week": int(row["week"]),
            "Date": match_date,
            "Home": h,
            "Away": a,
            "HG": hg,
            "AG": ag,
            "Score": f"{hg}-{ag}",
            "Winner": winner,
            "Expected Home": round(exp_h, 3),
            "Expected Away": round(exp_a, 3),
            "Underdog": underdog,
            "Upset Flag": upset_flag,
            "Upset Score": round(abs(act_h - exp_h), 3),
            "Elo Swing Home": round(delta_h, 2),
            "Elo Swing Away": round(delta_a, 2),
            "Total Impact": round(abs(delta_h) + abs(delta_a), 2),
        })

    power_rows = []
    for team in TEAMS:
        last3 = form_results[team][-3:]
        form_score = sum(last3) / max(len(last3), 1) if last3 else 0
        form_label = "".join(["W" if x == 3 else "D" if x == 1 else "L" for x in last3]) if last3 else "—"

        recent5 = team_match_points[team][-5:]
        momentum = round(sum(recent5) / max(len(recent5), 1), 2) if recent5 else 0

        power_score = elo[team] + ((form_score - 1.5) * 10) + ((momentum - 1.2) * 4)

        power_rows.append({
            "Team": team,
            "Power Score": round(power_score, 1),
            "Elo Rating": round(elo[team], 1),
            "Form": form_label,
            "Form Score": round(form_score, 2),
            "Momentum": round(momentum, 2),
        })

    pr = pd.DataFrame(power_rows).sort_values(["Power Score", "Elo Rating", "Team"], ascending=[False, False, True]).reset_index(drop=True)
    pr.index += 1
    pr.index.name = "Power Rank"

    match_analytics = pd.DataFrame(match_logs)

    # Team analytics
    standings = compute_standings(df).reset_index()
    pr_reset = pr.reset_index()

    power_map = {r["Team"]: r["Power Score"] for _, r in pr_reset.iterrows()}
    elo_map = {r["Team"]: r["Elo Rating"] for _, r in pr_reset.iterrows()}

    analytics_rows = []
    for _, row in standings.iterrows():
        team = row["Team"]
        gp = int(row["GP"])
        gf_pg = round(row["GF"] / gp, 2) if gp else 0
        ga_pg = round(row["GA"] / gp, 2) if gp else 0
        gd_pg = round((row["GF"] - row["GA"]) / gp, 2) if gp else 0

        opp_power = [power_map.get(o, 1500) for o in opps[team]] if opps[team] else []
        sos = round(float(np.mean(opp_power)), 1) if opp_power else 1500.0

        gd_std = round(float(np.std(team_goal_diffs[team])), 2) if team_goal_diffs[team] else 0.0
        if gp <= 1:
            consistency = "Early"
        elif gd_std <= 1.2:
            consistency = "Steady"
        elif gd_std <= 2.4:
            consistency = "Balanced"
        else:
            consistency = "Volatile"

        recent3_pts = sum(team_match_points[team][-3:]) if team_match_points[team] else 0
        season_ppg = row["PPG"]

        if gp < 2:
            trend = "Early"
        else:
            recent_ppg = recent3_pts / max(len(team_match_points[team][-3:]), 1)
            if recent_ppg > season_ppg + 0.4:
                trend = "Heating Up"
            elif recent_ppg < season_ppg - 0.4:
                trend = "Cooling"
            else:
                trend = "Stable"

        analytics_rows.append({
            "Team": team,
            "Power Score": power_map.get(team, 1500),
            "Elo Rating": elo_map.get(team, 1500),
            "PPG": season_ppg,
            "GF/Game": gf_pg,
            "GA/Game": ga_pg,
            "Raw GD/Game": gd_pg,
            "Strength of Schedule": sos,
            "Recent Form Pts": recent3_pts,
            "Consistency": consistency,
            "Trend": trend,
        })

    team_analytics = pd.DataFrame(analytics_rows)

    # Add composite projected score
    team_analytics["PPG_Norm"] = normalize_series(team_analytics["PPG"])
    team_analytics["Power_Norm"] = normalize_series(team_analytics["Power Score"])
    team_analytics["Form_Norm"] = normalize_series(team_analytics["Recent Form Pts"])
    team_analytics["SOS_Norm"] = normalize_series(team_analytics["Strength of Schedule"])

    team_analytics["Projected Score"] = (
        team_analytics["Power_Norm"] * 0.45
        + team_analytics["PPG_Norm"] * 0.35
        + team_analytics["Form_Norm"] * 0.10
        + team_analytics["SOS_Norm"] * 0.10
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


def compute_power_rankings(df: pd.DataFrame) -> pd.DataFrame:
    pr, _, _ = compute_power_package(df)
    return pr


def compute_power_movement(df: pd.DataFrame) -> dict:
    if df.empty:
        return {t: 0 for t in TEAMS}

    max_week = int(df["week"].max())
    prev_df = df[df["week"] < max_week]

    curr = compute_power_rankings(df).reset_index()
    curr_ranks = {r["Team"]: int(r["Power Rank"]) for _, r in curr.iterrows()}

    if prev_df.empty:
        return {t: 0 for t in TEAMS}

    prev = compute_power_rankings(prev_df).reset_index()
    prev_ranks = {r["Team"]: int(r["Power Rank"]) for _, r in prev.iterrows()}

    return {team: prev_ranks.get(team, len(TEAMS)) - curr_ranks.get(team, len(TEAMS)) for team in TEAMS}

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


def rank_medal(rank: int) -> str:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medals.get(rank, f"#{rank}")


def prep_match_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["game_date"] = out["game_date"].apply(format_display_date)
    return out

# ─────────────────────────────────────────────
# EXPORT HELPERS
# ─────────────────────────────────────────────

def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def make_power_rankings_png(pr: pd.DataFrame, movement: dict) -> bytes:
    width = 1400
    row_h = 105
    header_h = 180
    footer_h = 120
    height = header_h + len(pr) * row_h + footer_h + 40

    img = Image.new("RGB", (width, height), PFC_LIGHT)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
        font_sub = ImageFont.truetype("DejaVuSans.ttf", 24)
        font_rank = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        font_team = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
        font_meta = ImageFont.truetype("DejaVuSans.ttf", 22)
    except:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_rank = ImageFont.load_default()
        font_team = ImageFont.load_default()
        font_meta = ImageFont.load_default()

    draw.rectangle([0, 0, width, header_h], fill=PFC_NAVY)
    draw.text((40, 34), "U15 BOYS POWER RANKINGS", fill=PFC_WHITE, font=font_title)
    draw.text((44, 105), "Pensacola FC style snapshot", fill="#D9E3FF", font=font_sub)

    logo_path = find_logo_path()
    if logo_path:
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((180, 180))
            img.paste(logo, (width - 220, 5), logo)
        except:
            pass

    team_bar_colors = [PFC_BLUE, PFC_NAVY, "#2E4C95", "#4966B0", "#5977C1", "#6A88CF", "#809BDA", "#97AFEA"]

    y = header_h + 18
    pr_reset = pr.reset_index()

    for i, row in pr_reset.iterrows():
        bar_color = team_bar_colors[i % len(team_bar_colors)]
        draw.rounded_rectangle([35, y, width - 35, y + 82], radius=18, fill=bar_color)

        rank_text = f"{int(row['Power Rank'])}."
        draw.text((70, y + 15), rank_text, fill=PFC_WHITE, font=font_rank)
        draw.text((180, y + 14), str(row["Team"]).upper(), fill=PFC_WHITE, font=font_team)

        move = movement.get(row["Team"], 0)
        move_txt = movement_arrow(move)
        move_fill = movement_color(move)
        draw.text((width - 290, y + 16), move_txt, fill=move_fill, font=font_team)

        meta = f"Power {row['Power Score']}   |   Elo {row['Elo Rating']}   |   Form {row['Form']}"
        draw.text((182, y + 51), meta, fill="#E9EEFF", font=font_meta)

        y += row_h

    footer = (
        "Power rankings blend Elo rating, opponent strength, recent form, momentum, "
        "upset impact, and scoring margin. They are analytical only and separate from official standings."
    )
    wrapped = textwrap.fill(footer, width=110)
    draw.multiline_text((40, height - 95), wrapped, fill=PFC_DARK, font=font_meta, spacing=6)

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def make_league_summary_pdf(
    standings: pd.DataFrame,
    pr: pd.DataFrame,
    recent_results: pd.DataFrame,
    analytics_df: pd.DataFrame
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), leftMargin=30, rightMargin=30, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    story = []

    title = Paragraph("<b>Pensacola FC League Summary</b>", styles["Title"])
    subtitle = Paragraph(f"Generated on {datetime.now().strftime('%m/%d/%Y %I:%M %p')}", styles["Normal"])
    story.extend([title, subtitle, Spacer(1, 12)])

    def make_table(df, title_text):
        story.append(Paragraph(f"<b>{title_text}</b>", styles["Heading2"]))
        table_data = [list(df.columns)] + df.astype(str).values.tolist()
        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PFC_NAVY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F7F9FE")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F7F9FE"), colors.HexColor("#EEF3FD")]),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 14))

    standings_pdf = standings.reset_index()[["Rank", "Team", "GP", "W", "D", "L", "GF", "GA", "GD", "Pts"]]
    pr_pdf = pr.reset_index()[["Power Rank", "Team", "Power Score", "Elo Rating", "Form"]]
    analytics_pdf = analytics_df[["Team", "Strength of Schedule", "Trend", "Consistency", "Projected Rank", "Tier"]].copy()
    recent_pdf = recent_results[["Week", "Date", "Home", "Score", "Away", "Notes"]].copy() if not recent_results.empty else pd.DataFrame(columns=["Week", "Date", "Home", "Score", "Away", "Notes"])

    make_table(standings_pdf, "Official Standings")
    make_table(pr_pdf, "Power Rankings")
    make_table(analytics_pdf, "Advanced Analytics Snapshot")
    if not recent_pdf.empty:
        make_table(recent_pdf.head(8), "Recent Results")

    expl = Paragraph(
        "Power rankings are separate from official standings. They blend Elo rating, upset impact, margin of victory, recent form, momentum, and opponent strength to estimate current team strength.",
        styles["Normal"]
    )
    story.append(expl)

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# ─────────────────────────────────────────────
# CUSTOM CSS
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

        .section-header {{
            font-size: 1.35rem;
            font-weight: 900;
            color: {PFC_NAVY};
            border-bottom: 3px solid {PFC_BLUE};
            padding-bottom: 6px;
            margin-bottom: 16px;
            margin-top: 8px;
        }}

        .metric-card {{
            background: linear-gradient(135deg, {PFC_NAVY} 0%, {PFC_BLUE} 100%);
            border-radius: 14px;
            padding: 14px 16px;
            border: 1px solid {PFC_LIGHT_BLUE};
            box-shadow: 0 4px 14px rgba(27,47,107,.10);
        }}

        .metric-value {{
            font-size: 1.9rem;
            font-weight: 900;
            color: white;
            line-height: 1.05;
        }}

        .metric-label {{
            font-size: .78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #DCE5FF;
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

        .mini-card {{
            background: white;
            border: 1px solid #DCE5FF;
            border-radius: 12px;
            padding: 12px 14px;
            box-shadow: 0 2px 10px rgba(0,0,0,.04);
            height: 100%;
        }}

        .info-strip {{
            background: #EEF3FD;
            border-left: 5px solid {PFC_BLUE};
            border-radius: 10px;
            padding: 12px 14px;
            color: {PFC_DARK};
            margin-top: 12px;
        }}

        .pill {{
            display:inline-block;
            padding:4px 10px;
            border-radius:999px;
            background:{PFC_NAVY};
            color:white;
            font-weight:700;
            font-size:12px;
            margin-right:6px;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────
# PAGE: SCORE ENTRY
# ─────────────────────────────────────────────

def page_score_entry(df):
    st.markdown('<div class="section-header">📝 Score Entry & Match Management</div>', unsafe_allow_html=True)

    tab_add, tab_manage = st.tabs(["Add Match", "Edit / Delete Match"])

    with tab_add:
        with st.form("match_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                default_week = int(df["week"].max()) if not df.empty else 1
                week = st.number_input("Week", min_value=1, max_value=52, value=default_week, step=1)
                game_date = st.date_input("Game Date", value=date.today(), format="MM/DD/YYYY")
            with col2:
                home_team = st.selectbox("Home Team", TEAMS, key="add_home")
                home_goals = st.number_input("Home Goals", min_value=0, max_value=30, value=0, step=1)
            with col3:
                away_team = st.selectbox("Away Team", TEAMS, key="add_away")
                away_goals = st.number_input("Away Goals", min_value=0, max_value=30, value=0, step=1)

            notes = st.text_input("Notes (optional)", placeholder="e.g. Rain delay, rescheduled, forfeit")
            submitted = st.form_submit_button("⚽ Save Match", width="stretch")

        if submitted:
            if home_team == away_team:
                st.error("A team cannot play itself.")
            elif match_exists(week, game_date, home_team, away_team, home_goals, away_goals):
                st.warning("That exact match/result already exists. No duplicate was added.")
            else:
                insert_match(week, game_date, home_team, away_team, home_goals, away_goals, notes)
                st.success(f"Saved: {home_team} {home_goals} – {away_goals} {away_team} (Week {week})")
                st.rerun()

        if not df.empty:
            st.markdown("#### Recent Entries")
            recent = prep_match_display(df.tail(6).copy())
            recent["Score"] = recent["home_goals"].astype(str) + " – " + recent["away_goals"].astype(str)
            recent = recent[["week", "game_date", "home_team", "Score", "away_team", "notes"]]
            recent.columns = ["Week", "Date", "Home", "Score", "Away", "Notes"]
            st.dataframe(recent.iloc[::-1].reset_index(drop=True), width="stretch", hide_index=True)

    with tab_manage:
        if df.empty:
            st.info("No matches available to edit or delete.")
        else:
            manage_df = prep_match_display(df.copy())
            manage_df["match_label"] = manage_df.apply(
                lambda r: f"ID {r['id']} | Wk {r['week']} | {r['game_date']} | {r['home_team']} {r['home_goals']}-{r['away_goals']} {r['away_team']}",
                axis=1
            )

            selected_label = st.selectbox("Select match to edit/delete", manage_df["match_label"].tolist())
            selected_row = manage_df[manage_df["match_label"] == selected_label].iloc[0]

            with st.form("edit_match_form"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    edit_week = st.number_input("Week", min_value=1, max_value=52, value=int(selected_row["week"]), step=1, key="edit_week")
                    edit_date = st.date_input("Game Date", value=parse_to_date(selected_row["game_date"]), format="MM/DD/YYYY", key="edit_date")
                with c2:
                    edit_home = st.selectbox("Home Team", TEAMS, index=TEAMS.index(selected_row["home_team"]), key="edit_home")
                    edit_hg = st.number_input("Home Goals", min_value=0, max_value=30, value=int(selected_row["home_goals"]), step=1, key="edit_hg")
                with c3:
                    edit_away = st.selectbox("Away Team", TEAMS, index=TEAMS.index(selected_row["away_team"]), key="edit_away")
                    edit_ag = st.number_input("Away Goals", min_value=0, max_value=30, value=int(selected_row["away_goals"]), step=1, key="edit_ag")

                edit_notes = st.text_input("Notes", value=selected_row["notes"], key="edit_notes")

                save_col, delete_col = st.columns(2)
                save_changes = save_col.form_submit_button("💾 Save Changes", width="stretch")
                delete_selected = delete_col.form_submit_button("🗑️ Delete Match", width="stretch")

            if save_changes:
                if edit_home == edit_away:
                    st.error("A team cannot play itself.")
                elif match_exists(edit_week, edit_date, edit_home, edit_away, edit_hg, edit_ag, exclude_id=int(selected_row["id"])):
                    st.warning("That exact edited match/result already exists. Changes were not saved.")
                else:
                    update_match(int(selected_row["id"]), edit_week, edit_date, edit_home, edit_away, edit_hg, edit_ag, edit_notes)
                    st.success("Match updated.")
                    st.rerun()

            if delete_selected:
                delete_match(int(selected_row["id"]))
                st.success("Match deleted.")
                st.rerun()

# ─────────────────────────────────────────────
# PAGE: MATCH HISTORY
# ─────────────────────────────────────────────

def page_match_history(df):
    st.markdown('<div class="section-header">📋 Match History</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No matches recorded yet.")
        return

    col1, col2 = st.columns(2)
    with col1:
        weeks = ["All"] + sorted(df["week"].unique().tolist())
        sel_week = st.selectbox("Filter by Week", weeks)
    with col2:
        team_list = ["All"] + sorted(TEAMS)
        sel_team = st.selectbox("Filter by Team", team_list)

    filtered = df.copy()
    if sel_week != "All":
        filtered = filtered[filtered["week"] == sel_week]
    if sel_team != "All":
        filtered = filtered[(filtered["home_team"] == sel_team) | (filtered["away_team"] == sel_team)]

    display = prep_match_display(filtered.copy())
    display["Score"] = display["home_goals"].astype(str) + " – " + display["away_goals"].astype(str)
    display = display[["week", "game_date", "home_team", "Score", "away_team", "notes"]]
    display.columns = ["Week", "Date", "Home", "Score", "Away", "Notes"]

    st.dataframe(display.reset_index(drop=True), width="stretch", hide_index=True)
    st.caption(f"Showing {len(display)} match(es)")

# ─────────────────────────────────────────────
# PAGE: STANDINGS
# ─────────────────────────────────────────────

def page_standings(df):
    st.markdown('<div class="section-header">🏆 Official Standings</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="info-strip">
        <b>Official rules:</b> Win = 3 points, Draw = 1 point, Loss = 0 points.
        Goal differential is capped at <b>±4 per match</b> for standings only.
        </div>
        """,
        unsafe_allow_html=True,
    )

    standings = compute_standings(df).reset_index()
    movement = compute_standings_movement(df)

    standings["Move"] = standings["Team"].apply(lambda t: movement_arrow(movement.get(t, 0)))
    standings = standings[["Rank", "Team", "Move", "GP", "W", "D", "L", "GF", "GA", "GD", "Pts", "PPG"]]

    st.dataframe(standings, width="stretch", hide_index=True)

    if not df.empty:
        st.markdown("#### Quick Standings Insights")
        base = compute_standings(df)
        c1, c2, c3, c4 = st.columns(4)
        leader = base.iloc[0]
        top_gf = base.sort_values("GF", ascending=False).iloc[0]
        best_def = base.sort_values("GA", ascending=True).iloc[0]
        most_wins = base.sort_values("W", ascending=False).iloc[0]

        c1.metric("League Leader", leader["Team"], f"{int(leader['Pts'])} pts")
        c2.metric("Top Attack", top_gf["Team"], f"{int(top_gf['GF'])} goals")
        c3.metric("Best Defense", best_def["Team"], f"{int(best_def['GA'])} against")
        c4.metric("Most Wins", most_wins["Team"], f"{int(most_wins['W'])} wins")

# ─────────────────────────────────────────────
# PAGE: POWER RANKINGS
# ─────────────────────────────────────────────

def page_power_rankings(df):
    st.markdown('<div class="section-header">⚡ Power Rankings</div>', unsafe_allow_html=True)

    pr, match_analytics, team_analytics = compute_power_package(df)
    movement = compute_power_movement(df)

    display = pr.reset_index().copy()
    display["Move"] = display["Team"].apply(lambda t: movement_arrow(movement.get(t, 0)))
    display = display[["Power Rank", "Team", "Move", "Power Score", "Elo Rating", "Form", "Momentum"]]
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
                <div style="min-width:80px;text-align:center;">{form_html}</div>
                <div style="min-width:56px;text-align:right;font-weight:900;color:{arrow_color};">{arrow}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="info-strip">
        <b>How power rankings work:</b> These are not the official standings.
        Power rankings estimate team strength using Elo rating, opponent strength,
        upset impact, uncapped scoring margin, recent form, and momentum. A favorite
        that loses takes a bigger hit, while an underdog that wins gets rewarded more.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not match_analytics.empty:
        upsets = match_analytics[match_analytics["Upset Flag"]].sort_values(["Upset Score", "Total Impact"], ascending=False)
        st.markdown("#### Upset Tracker")
        if upsets.empty:
            st.info("No major upsets flagged yet.")
        else:
            show_upsets = upsets.copy()
            show_upsets["Date"] = show_upsets["Date"].apply(format_display_date)
            show_upsets["Match"] = show_upsets["Home"] + " " + show_upsets["Score"] + " " + show_upsets["Away"]
            st.dataframe(
                show_upsets[["Week", "Date", "Match", "Underdog", "Winner", "Upset Score", "Total Impact"]].head(8),
                width="stretch",
                hide_index=True,
            )

# ─────────────────────────────────────────────
# PAGE: DASHBOARD
# ─────────────────────────────────────────────

def page_dashboard(df):
    st.markdown('<div class="section-header">📊 League Dashboard</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No match data yet.")
        return

    standings = compute_standings(df)
    pr, match_analytics, team_analytics = compute_power_package(df)
    power_movement = compute_power_movement(df)
    standings_movement = compute_standings_movement(df)

    total_goals = int(df["home_goals"].sum() + df["away_goals"].sum())
    avg_goals = round(total_goals / max(len(df), 1), 1)
    current_week = int(df["week"].max())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Goals", total_goals)
    m2.metric("Avg Goals / Match", avg_goals)
    m3.metric("Matches Played", len(df))
    m4.metric("Current Week", current_week)

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
        pr_display = pr_display[["Power Rank", "Team", "Move", "Power Score", "Elo Rating", "Form"]]
        st.dataframe(pr_display, width="stretch", hide_index=True)

    st.divider()

    st.markdown("#### Advanced Analytics Spotlight")
    c1, c2, c3, c4 = st.columns(4)

    best_attack = team_analytics.sort_values("GF/Game", ascending=False).iloc[0]
    best_defense = team_analytics.sort_values("GA/Game", ascending=True).iloc[0]
    toughest_sched = team_analytics.sort_values("Strength of Schedule", ascending=False).iloc[0]
    most_consistent = team_analytics.assign(_rank=team_analytics["Consistency"].map({"Steady": 1, "Balanced": 2, "Volatile": 3, "Early": 4})).sort_values(["_rank", "Projected Score"], ascending=[True, False]).iloc[0]

    with c1:
        st.markdown(f'<div class="mini-card"><b>Best Attack</b><br><span style="font-size:1.2rem;font-weight:900;color:{PFC_NAVY};">{best_attack["Team"]}</span><br>{best_attack["GF/Game"]} goals/game</div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="mini-card"><b>Best Defense</b><br><span style="font-size:1.2rem;font-weight:900;color:{PFC_NAVY};">{best_defense["Team"]}</span><br>{best_defense["GA/Game"]} allowed/game</div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="mini-card"><b>Toughest Schedule</b><br><span style="font-size:1.2rem;font-weight:900;color:{PFC_NAVY};">{toughest_sched["Team"]}</span><br>SOS {toughest_sched["Strength of Schedule"]}</div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="mini-card"><b>Most Consistent</b><br><span style="font-size:1.2rem;font-weight:900;color:{PFC_NAVY};">{most_consistent["Team"]}</span><br>{most_consistent["Consistency"]}</div>', unsafe_allow_html=True)

    st.divider()

    st.markdown("#### Visual Power Rankings")
    for _, row in pr.reset_index().iterrows():
        team = row["Team"]
        delta = power_movement.get(team, 0)
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
                <div style="min-width:80px;text-align:center;">{form_html}</div>
                <div style="min-width:56px;text-align:right;font-weight:900;color:{arrow_color};">{arrow}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.markdown("#### Points by Team")
        pts_df = standings.reset_index()[["Team", "Pts"]].sort_values("Pts", ascending=False)
        fig_pts = px.bar(
            pts_df,
            x="Team",
            y="Pts",
            text="Pts",
            color="Pts",
            color_continuous_scale=["#C9D7FA", PFC_NAVY]
        )
        fig_pts.update_traces(textposition="outside")
        fig_pts.update_layout(
            paper_bgcolor=PFC_WHITE,
            plot_bgcolor=PFC_WHITE,
            font_color=PFC_DARK,
            showlegend=False,
            coloraxis_showscale=False,
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig_pts, width="stretch")

    with chart_right:
        st.markdown("#### Goals For vs Goals Against")
        gf_ga = standings.reset_index()[["Team", "GF", "GA"]].sort_values("GF", ascending=False)
        fig_gfga = go.Figure()
        fig_gfga.add_trace(go.Bar(name="Goals For", x=gf_ga["Team"], y=gf_ga["GF"], marker_color=PFC_BLUE))
        fig_gfga.add_trace(go.Bar(name="Goals Against", x=gf_ga["Team"], y=gf_ga["GA"], marker_color=PFC_SILVER))
        fig_gfga.update_layout(
            barmode="group",
            paper_bgcolor=PFC_WHITE,
            plot_bgcolor=PFC_WHITE,
            font_color=PFC_DARK,
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig_gfga, width="stretch")

    st.divider()

    lower_left, lower_right = st.columns(2)

    with lower_left:
        st.markdown("#### Recent Results")
        recent = prep_match_display(df.sort_values(["week", "game_date", "id"], ascending=False).head(6).copy())
        for _, row in recent.iterrows():
            st.markdown(
                f"**Wk {int(row['week'])}** · {row['game_date']} · "
                f"{row['home_team']} **{int(row['home_goals'])}-{int(row['away_goals'])}** {row['away_team']}"
                + (f"  —  *{row['notes']}*" if row["notes"] else "")
            )

        st.markdown("#### Match Impact View")
        if not match_analytics.empty:
            impact = match_analytics.copy().sort_values(["Total Impact", "Upset Score"], ascending=False).head(5)
            impact["Date"] = impact["Date"].apply(format_display_date)
            impact["Match"] = impact["Home"] + " " + impact["Score"] + " " + impact["Away"]
            st.dataframe(impact[["Week", "Date", "Match", "Winner", "Underdog", "Total Impact"]], width="stretch", hide_index=True)

    with lower_right:
        st.markdown("#### Projected Table Insights")
        proj = team_analytics.sort_values(["Projected Rank"]).copy()
        st.dataframe(
            proj[["Projected Rank", "Team", "Tier", "Trend", "Strength of Schedule", "Projected Score"]]
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

    st.markdown(
        f"""
        <div class="info-strip">
        <b>Analytics notes:</b> Official standings still use capped goal differential.
        Power rankings and advanced analytics use uncapped scoring margin, Elo movement,
        opponent quality, recent form, and momentum to better estimate real current strength.
        </div>
        """,
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
# PAGE: NOTES
# ─────────────────────────────────────────────

def page_notes():
    st.markdown('<div class="section-header">📣 League Notes & Announcements</div>', unsafe_allow_html=True)

    with st.form("note_form", clear_on_submit=True):
        note_text = st.text_area(
            "Add a new note or announcement",
            height=120,
            placeholder="e.g. Next games moved to Saturday due to field maintenance..."
        )
        submitted = st.form_submit_button("📌 Post Note", width="stretch")

    if submitted and note_text.strip():
        insert_note(note_text.strip())
        st.success("Note posted.")
        st.rerun()

    notes_df = load_notes()
    if notes_df.empty:
        st.info("No notes yet.")
    else:
        for _, row in notes_df.iterrows():
            created_fmt = format_display_date(str(row["created"]).split(" ")[0]) + " " + str(row["created"]).split(" ")[1] if " " in str(row["created"]) else row["created"]
            with st.expander(f"📌 {created_fmt}", expanded=True):
                st.write(row["note_text"])
                if st.button("🗑️ Delete", key=f"del_note_{row['id']}"):
                    delete_note(row["id"])
                    st.rerun()

# ─────────────────────────────────────────────
# PAGE: EXPORT CENTER
# ─────────────────────────────────────────────

def page_export(df):
    st.markdown('<div class="section-header">📥 Export Center</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No data to export yet.")
        return

    standings = compute_standings(df)
    pr, _, team_analytics = compute_power_package(df)
    movement = compute_power_movement(df)

    history_export = prep_match_display(df.copy())
    history_export["Score"] = history_export["home_goals"].astype(str) + " – " + history_export["away_goals"].astype(str)
    history_export = history_export[["week", "game_date", "home_team", "Score", "away_team", "notes"]]
    history_export.columns = ["Week", "Date", "Home", "Score", "Away", "Notes"]

    pdf_bytes = make_league_summary_pdf(
        standings=standings,
        pr=pr,
        recent_results=history_export,
        analytics_df=team_analytics
    )
    png_bytes = make_power_rankings_png(pr, movement)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.download_button(
            "📄 League Summary PDF",
            data=pdf_bytes,
            file_name=f"league_summary_{datetime.now().strftime('%m%d%Y')}.pdf",
            mime="application/pdf",
            width="stretch",
        )

    with col2:
        st.download_button(
            "🖼️ Power Rankings PNG",
            data=png_bytes,
            file_name=f"power_rankings_{datetime.now().strftime('%m%d%Y')}.png",
            mime="image/png",
            width="stretch",
        )

    with col3:
        st.download_button(
            "📋 Standings CSV",
            data=df_to_csv_bytes(standings.reset_index()),
            file_name="standings.csv",
            mime="text/csv",
            width="stretch",
        )

    with col4:
        st.download_button(
            "📅 Match History CSV",
            data=df_to_csv_bytes(history_export),
            file_name="match_history.csv",
            mime="text/csv",
            width="stretch",
        )

    st.divider()
    st.markdown("#### Export Preview")
    preview_left, preview_right = st.columns(2)
    with preview_left:
        st.markdown("**Official Standings**")
        st.dataframe(standings.reset_index()[["Rank", "Team", "GP", "W", "D", "L", "GD", "Pts"]], width="stretch", hide_index=True)
    with preview_right:
        st.markdown("**Power Rankings**")
        st.dataframe(pr.reset_index()[["Power Rank", "Team", "Power Score", "Elo Rating", "Form"]], width="stretch", hide_index=True)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    init_db()
    inject_css()

    render_header()

    logo_path = find_logo_path()
    if logo_path:
        st.sidebar.image(logo_path, width=140)
    else:
        st.sidebar.markdown("## ⚽")

    st.sidebar.title("League Navigation")
    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigate",
        [
            "📊 Dashboard",
            "📝 Score Entry",
            "📋 Match History",
            "🏆 Standings",
            "⚡ Power Rankings",
            "📣 Notes",
            "📥 Export",
        ],
        label_visibility="collapsed",
    )

    df = load_matches()

    if not df.empty:
        st.sidebar.divider()
        st.sidebar.markdown("**League Summary**")
        st.sidebar.caption(f"Matches: **{len(df)}**")
        st.sidebar.caption(f"Weeks Logged: **{int(df['week'].max())}**")
        total_goals = int(df["home_goals"].sum() + df["away_goals"].sum())
        st.sidebar.caption(f"Goals Scored: **{total_goals}**")
        st.sidebar.caption(f"Data Saved In: **{DB_PATH}**")

    st.sidebar.divider()
    st.sidebar.caption("Built for youth soccer league admins.")

    if page == "📊 Dashboard":
        page_dashboard(df)
    elif page == "📝 Score Entry":
        page_score_entry(df)
    elif page == "📋 Match History":
        page_match_history(df)
    elif page == "🏆 Standings":
        page_standings(df)
    elif page == "⚡ Power Rankings":
        page_power_rankings(df)
    elif page == "📣 Notes":
        page_notes()
    elif page == "📥 Export":
        page_export(df)


if __name__ == "__main__":
    main()