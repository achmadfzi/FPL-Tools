import html as _html
from datetime import datetime

import streamlit as st

from .api import CACHE_FILE, BASE_URL, get_game_data
from .model import build_projection_table
from .utils import FDR_LABELS, STATUS_LABELS, fmt_deadline_wib, fmt_price


@st.cache_data(ttl=300, show_spinner="Memuat data FPL...")
def load_data():
    gd = get_game_data()
    df = build_projection_table(gd)
    return gd, df


def refresh():
    from .api import clear_cache

    clear_cache()
    st.cache_data.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Jersey color mapping by team short name (Premier League 2026/27 home kits)
# ---------------------------------------------------------------------------
JERSEY_COLORS = {
    "ARS": ("#EF0107", "#fff"),
    "AVL": ("#670E36", "#89D1F0"),
    "BOU": ("#DA291C", "#000"),
    "BRE": ("#e30613", "#fff"),
    "BHA": ("#0057B8", "#fff"),
    "CHE": ("#034694", "#fff"),
    "CRY": ("#1B458F", "#C4122E"),
    "EVE": ("#003399", "#fff"),
    "FUL": ("#fff", "#000"),
    "IPS": ("#0000FF", "#fff"),
    "LEE": ("#fff", "#1D428A"),
    "LIV": ("#C8102E", "#fff"),
    "MCI": ("#6CABDD", "#1C2C5B"),
    "MUN": ("#DA291C", "#fff"),
    "NEW": ("#241F20", "#fff"),
    "NFO": ("#DD0000", "#fff"),
    "SUN": ("#EB172B", "#fff"),
    "TOT": ("#fff", "#132257"),
    "WHU": ("#7A263A", "#1BB1E7"),
    "WOL": ("#FDB913", "#000"),
    "COV": ("#0092D4", "#fff"),
}

# FDR cell colors (background, text) - Strong vibrant FPL palette
FDR_CELL = {
    1: ("#01FC7A", "#064420"),
    2: ("#01FC7A", "#064420"),
    3: ("#e2e8f0", "#1e293b"),
    4: ("#FF1751", "#ffffff"),
    5: ("#80072D", "#ffffff"),
}

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');

/* ── GLOBAL & BASE TYPOGRAPHY ──────────────────────── */
html, body, [class*="css"], [data-testid="stAppViewContainer"], [data-testid="stMarkdownContainer"] {
  font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  color: #0f172a;
  -webkit-font-smoothing: antialiased;
}
[data-testid="stAppViewContainer"] { background: #f8fafc; }
[data-testid="stHeader"] { background: transparent; }

#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1.25rem; max-width: 1360px; }
h1, h2, h3, h4, h5, h6 { color: #0f172a !important; font-weight: 600; letter-spacing: -0.02em; }
p, span, div, label { color: inherit; }

/* Sidebar */
.stApp [data-testid="stSidebar"] {
  background: #ffffff;
  border-right: 1px solid #e2e8f0;
}
.stApp [data-testid="stSidebar"] label, .stApp [data-testid="stSidebar"] p {
  color: #334155 !important;
  font-size: 0.85rem;
}

/* ── HERO HEADER (MODERN MINIMALIST) ─────────────────── */
.fpl-hero {
  background: linear-gradient(135deg, #1e0024 0%, #37003c 55%, #4c0053 100%);
  border-radius: 16px;
  padding: 24px 30px 20px;
  margin-bottom: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 4px 20px -2px rgba(55, 0, 60, 0.12);
}
.fpl-hero .kicker {
  letter-spacing: 2.5px;
  text-transform: uppercase;
  font-size: .68rem;
  color: #00ff87;
  font-weight: 600;
}
.fpl-hero h1 {
  font-size: 1.75rem;
  font-weight: 700;
  margin: 6px 0 4px;
  color: #ffffff !important;
  letter-spacing: -0.02em;
}
.fpl-hero .sub {
  color: #e2d9eb;
  font-size: .875rem;
  margin: 0;
  font-weight: 400;
}
.fpl-hero .updated {
  color: rgba(255, 255, 255, 0.65);
  font-size: .75rem;
  margin-top: 6px;
}

/* ── COUNTDOWN ─────────────────────────────────────── */
.countdown { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.cd-box {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  padding: 6px 12px;
  text-align: center;
  min-width: 64px;
}
.cd-box .num { font-size: 1.2rem; font-weight: 600; color: #fff; line-height: 1.2; }
.cd-box .lab { font-size: .56rem; text-transform: uppercase; letter-spacing: 1px; color: rgba(255, 255, 255, 0.65); }

/* ── STAT HEADER BAR ───────────────────────────────── */
.stat-bar {
  display: flex;
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  margin-bottom: 16px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}
.stat-item {
  flex: 1;
  text-align: center;
  padding: 14px 10px;
  border-right: 1px solid #f1f5f9;
}
.stat-item:last-child { border-right: none; }
.stat-item .sv { font-size: 1.2rem; font-weight: 600; color: #0f172a; }
.stat-item .sl { font-size: .65rem; text-transform: uppercase; letter-spacing: 1px; color: #64748b; font-weight: 500; margin-top: 2px; }

/* ── CARDS ──────────────────────────────────────────── */
.fpl-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}
.fpl-card h3 { margin: 0 0 6px; font-size: .95rem; font-weight: 600; color: #0f172a !important; }
.fpl-card .card-sub { color: #64748b; font-size: .8rem; margin-bottom: 12px; font-weight: 400; }

/* Player card (standalone) */
.p-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 12px 12px;
  text-align: center;
  position: relative;
  height: 100%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.p-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}
.p-card img { width: 62px; height: 78px; object-fit: contain; border-radius: 6px; background: #f8fafc; }
.p-card .p-name { font-weight: 600; font-size: .875rem; margin-top: 8px; color: #0f172a; }
.p-card .p-team { font-size: .7rem; color: #64748b; text-transform: uppercase; letter-spacing: .5px; margin-top: 2px; }
.p-card .p-proj { font-size: 1.15rem; font-weight: 600; color: #37003c; margin-top: 4px; }
.p-card .p-fixture { font-size: .7rem; color: #475569; margin-top: 4px; font-weight: 400; }
.p-card .p-sub { font-size: .68rem; color: #64748b; margin-top: 2px; }
.p-card .tag {
  position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
  background: #37003c; color: #fff; font-weight: 600; font-size: .6rem;
  letter-spacing: 1px; padding: 2px 10px; border-radius: 99px; white-space: nowrap;
}
.p-card .tag.vice { background: #ea580c; color: #fff; }
.p-card .tag.alt { background: #4f46e5; color: #fff; }

/* ── BADGES (STRONG VIBRANT SOLID PILLS) ───────────── */
.fdr-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: .65rem;
  font-weight: 600;
}
.fdr-1 { background: #01FC7A; color: #064420; }
.fdr-2 { background: #01FC7A; color: #064420; }
.fdr-3 { background: #e2e8f0; color: #1e293b; }
.fdr-4 { background: #FF1751; color: #ffffff; }
.fdr-5 { background: #80072D; color: #ffffff; }

.pos-badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: .64rem;
  font-weight: 600;
  color: #ffffff !important;
}
.pos-GK { background: #d97706; }
.pos-DEF { background: #2563eb; }
.pos-MID { background: #16a34a; }
.pos-FWD { background: #dc2626; }

/* ── PITCH V2 (CLEAN REALISTIC TACTICAL FORMATION) ──── */
.pitch-v2 {
  position: relative;
  background: linear-gradient(180deg, #107c41 0%, #0d6e38 25%, #107c41 50%, #0d6e38 75%, #107c41 100%);
  border-radius: 14px;
  padding: 24px 10px 20px;
  border: 2px solid #095028;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
  min-height: 490px;
  box-shadow: inset 0 0 35px rgba(0, 0, 0, 0.18);
}
.pitch-v2::after {
  content: ""; position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
  width: 90px; height: 90px; border: 1.5px solid rgba(255, 255, 255, 0.25); border-radius: 50%;
  pointer-events: none;
}
.pitch-v2::before {
  content: ""; position: absolute; left: 0; right: 0; top: 50%; height: 1.5px;
  background: rgba(255, 255, 255, 0.22); pointer-events: none;
}
.p-row-v2 {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
  z-index: 1;
  flex-wrap: nowrap;
}

/* Compact realistic player cell on pitch */
.pc {
  background: #ffffff;
  border-radius: 6px;
  padding: 4px 2px 3px;
  width: 78px;
  text-align: center;
  position: relative;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.85);
  transition: transform 0.1s ease;
}
.pc:hover { transform: scale(1.04); z-index: 2; }
.pc.captain { border: 1.5px solid #37003c; box-shadow: 0 0 8px rgba(55, 0, 60, 0.35); }
.pc .pc-img { width: 32px; height: 38px; object-fit: contain; margin: 0 auto; display: block; }
.pc .pc-jersey {
  width: 28px; height: 32px; margin: 0 auto; border-radius: 3px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: .6rem; color: #fff;
}
.pc .pc-name {
  font-size: .64rem; font-weight: 600; color: #0f172a; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; max-width: 74px; margin: 2px auto 0;
  line-height: 1.15;
}
.pc .pc-team {
  font-size: .52rem; font-weight: 500; color: #fff; line-height: 1.1;
  margin: 1px auto 0; background: #37003c; border-radius: 3px;
  padding: 0.5px 5px; display: inline-block; letter-spacing: .3px;
}
.pc .pc-price { font-size: .56rem; color: #64748b; font-weight: 400; line-height: 1.1; }
.pc .pc-cap {
  position: absolute; top: -5px; left: -4px; width: 16px; height: 16px;
  background: #37003c; color: #fff; border-radius: 50%; font-size: .52rem;
  font-weight: 700; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.pc .pc-vice {
  position: absolute; top: -5px; left: -4px; width: 16px; height: 16px;
  background: #ea580c; color: #fff; border-radius: 50%; font-size: .52rem;
  font-weight: 700; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}

/* GW mini projection cells */
.gw-cells { display: flex; gap: 1.5px; margin-top: 2px; border-radius: 3px; overflow: hidden; }
.gw-cell {
  flex: 1; text-align: center; padding: 1.5px 0.5px;
  font-size: .54rem; line-height: 1.15; border-radius: 2px;
}
.gw-cell .gv { font-size: .58rem; font-weight: 600; }
.gw-cell .gl { font-size: .46rem; font-weight: 400; opacity: 0.9; }

/* ── BENCH V2 (COMPACT) ────────────────────────────── */
.bench-v2 {
  display: flex; gap: 8px; justify-content: center; background: #f1f5f9;
  border-radius: 10px; padding: 10px 12px; margin-top: 10px; align-items: flex-start;
  border: 1px solid #e2e8f0;
}
.bench-v2 .bc {
  background: #ffffff; border-radius: 6px; padding: 4px; text-align: center;
  width: 78px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0;
}
.bench-v2 .bc .pc-img { width: 28px; height: 34px; }
.bench-v2 .bc .pc-name {
  font-size: .62rem; font-weight: 600; color: #0f172a; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; max-width: 70px; margin: 2px auto 0;
}
.bench-v2 .bc .pos-label {
  font-size: .52rem; font-weight: 600; color: #64748b; text-transform: uppercase;
  letter-spacing: .5px; margin-bottom: 2px;
}

/* ── PICKER PANEL ──────────────────────────────────── */
.picker {
  background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 16px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03); height: 100%;
}
.picker h3 { margin: 0 0 10px; font-size: .95rem; font-weight: 600; color: #0f172a !important; }
.pick-row {
  display: flex; align-items: center; gap: 8px; padding: 7px 4px;
  border-bottom: 1px solid #f1f5f9; font-size: .75rem;
}
.pick-row:hover { background: #f8fafc; }
.pick-row .pr-name { font-weight: 500; color: #0f172a; flex: 1; }
.pick-row .pr-team { font-size: .68rem; color: #64748b; font-weight: 400; }
.pick-row .pr-price { font-size: .7rem; color: #475569; min-width: 45px; }
.pick-row .pr-proj { font-weight: 600; color: #37003c; min-width: 36px; text-align: right; }
.pick-rec {
  background: #f5f3ff;
  border: 1px solid #ddd6fe; border-radius: 6px; padding: 2px 7px;
  font-size: .6rem; font-weight: 500; color: #6d28d9;
}

/* ── GW TOGGLE ─────────────────────────────────────── */
.gw-toggle {
  display: inline-flex; background: #e2e8f0; border-radius: 8px; overflow: hidden;
  margin-bottom: 12px;
}
.gw-toggle .gt { padding: 5px 16px; font-size: .75rem; font-weight: 500; color: #475569; cursor: pointer; }
.gw-toggle .gt.active { background: #37003c; color: #fff; }

/* ── METRICS (CLEAN MODERN) ────────────────────────── */
[data-testid="stMetric"] {
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 12px !important;
  padding: 14px 16px !important;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03) !important;
}
[data-testid="stMetric"] label, [data-testid="stMetric"] [data-testid="stMetricLabel"] {
  color: #64748b !important;
  font-weight: 500 !important;
  font-size: .75rem !important;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {
  color: #0f172a !important;
  font-weight: 600 !important;
  font-size: 1.35rem !important;
}

/* ── SECTION HEADERS ───────────────────────────────── */
.section { margin: 24px 0 10px; font-size: 1.05rem; font-weight: 600; color: #0f172a !important; letter-spacing: -0.01em; }
.section em { color: #37003c; font-style: normal; font-weight: 600; }

/* ── TABLES & DATAFRAMES (CLEAN MINIMAL) ───────────── */
[data-testid="stDataFrame"] {
  border: 1px solid #e2e8f0 !important;
  border-radius: 10px !important;
  overflow: hidden !important;
  background-color: #ffffff !important;
}
table {
  width: 100% !important;
  border-collapse: collapse !important;
  color: #1e293b !important;
  font-size: 0.8125rem;
}
th {
  background-color: #f8fafc !important;
  color: #475569 !important;
  font-weight: 500 !important;
  font-size: 0.75rem !important;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid #e2e8f0 !important;
  padding: 8px 10px !important;
}
td {
  color: #1e293b !important;
  font-weight: 400;
  border-bottom: 1px solid #f1f5f9 !important;
  padding: 8px 10px !important;
}
tr:hover td {
  background-color: #f8fafc !important;
}

/* ── EXPANDERS ─────────────────────────────────────── */
.stExpander { background: #ffffff !important; border: 1px solid #e2e8f0 !important; border-radius: 10px !important; }
[data-testid="stExpanderDetails"] { background: #ffffff !important; color: #1e293b !important; }
.stExpander summary, [data-testid="stExpander"] summary span { color: #0f172a !important; font-weight: 500 !important; font-size: 0.875rem !important; }

/* ── BUTTONS ───────────────────────────────────────── */
[data-testid="stButton"] button,
button[data-testid="stBaseButton-secondary"],
button[data-testid="stBaseButton-primary"],
[data-testid="stFormSubmitButton"] button {
  background: #37003c !important;
  border: 1px solid #4a0052 !important;
  color: #ffffff !important;
  border-radius: 8px !important;
  font-weight: 500 !important;
  font-size: 0.85rem !important;
  padding: 6px 16px !important;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
}
[data-testid="stButton"] button p,
[data-testid="stButton"] button span,
[data-testid="stButton"] button div,
button[data-testid="stBaseButton-secondary"] p,
button[data-testid="stBaseButton-secondary"] span,
button[data-testid="stBaseButton-primary"] p,
button[data-testid="stBaseButton-primary"] span,
[data-testid="stFormSubmitButton"] button p,
[data-testid="stFormSubmitButton"] button span {
  color: #ffffff !important;
  font-weight: 500 !important;
}
[data-testid="stButton"] button:hover,
button[data-testid="stBaseButton-secondary"]:hover,
button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stFormSubmitButton"] button:hover {
  border-color: #00ff87 !important;
  background: #4a0050 !important;
}
[data-testid="stButton"] button:disabled,
[data-testid="stButton"] button[disabled],
button[data-testid="stBaseButton-secondary"]:disabled,
button[data-testid="stBaseButton-primary"]:disabled,
[data-testid="stFormSubmitButton"] button:disabled {
  background: #f1f5f9 !important;
  border-color: #e2e8f0 !important;
}
[data-testid="stButton"] button:disabled p,
[data-testid="stButton"] button:disabled span,
[data-testid="stButton"] button:disabled div,
button[data-testid="stBaseButton-secondary"]:disabled p,
button[data-testid="stBaseButton-primary"]:disabled p,
[data-testid="stFormSubmitButton"] button:disabled p {
  color: #94a3b8 !important;
}

/* ── MULTISELECT & FORM INPUTS ─────────────────────── */
[data-baseweb="tag"] {
  background-color: #f1f5f9 !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 6px !important;
}
[data-baseweb="tag"] span {
  color: #0f172a !important;
  font-weight: 500 !important;
  font-size: 0.78rem !important;
}
[data-baseweb="tag"] svg, [data-baseweb="tag"] [data-testid="stIcon"] {
  color: #64748b !important;
  fill: #64748b !important;
}
[data-baseweb="select"] {
  background-color: #ffffff !important;
}
[data-baseweb="select"] div {
  color: #0f172a !important;
}
[data-baseweb="select"] input {
  color: #0f172a !important;
}
[data-baseweb="select"] input::placeholder {
  color: #94a3b8 !important;
}
[data-baseweb="popover"], [data-baseweb="menu"] {
  background-color: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08) !important;
}
li[role="option"] {
  color: #0f172a !important;
  font-size: 0.825rem !important;
}
li[role="option"]:hover, li[aria-selected="true"] {
  background-color: #f8fafc !important;
  color: #37003c !important;
  font-weight: 500 !important;
}
[data-testid="stWidgetLabel"] label, [data-testid="stWidgetLabel"] p {
  color: #334155 !important;
  font-weight: 500 !important;
  font-size: 0.825rem !important;
}

/* ── BENCH ROW (legacy) ────────────────────────────── */
.bench-row { display: flex; gap: 8px; flex-wrap: wrap; }
.bench-cell {
  background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 8px 12px; display: flex; align-items: center; gap: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}
.bench-cell img { width: 24px; height: 30px; object-fit: contain; }
.bench-cell .n { font-size: .76rem; font-weight: 600; color: #0f172a; }
.bench-cell .x { font-size: .72rem; font-weight: 400; color: #64748b; }

/* ── BAR CHART ─────────────────────────────────────── */
.bar-row { display: flex; align-items: center; gap: 8px; margin: 6px 0; font-size: .75rem; }
.bar-label { width: 160px; color: #64748b; text-align: right; flex-shrink: 0; font-weight: 400; }
.bar-track { flex: 1; background: #f1f5f9; border-radius: 99px; height: 8px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 99px; }
.bar-val { width: 46px; color: #0f172a; font-weight: 600; flex-shrink: 0; }

/* ── PITCH LEGACY (p-cell) ─────────────────────────── */
.pitch {
  position: relative;
  background: linear-gradient(180deg, #107c41 0%, #0d6e38 50%, #107c41 100%);
  border-radius: 14px; padding: 18px 12px; border: 1px solid #095028;
  display: flex; flex-direction: column; gap: 16px;
  box-shadow: inset 0 0 30px rgba(0,0,0,.12);
}
.pitch::before { content: ""; position: absolute; left: 0; right: 0; top: 50%; height: 1.5px; background: rgba(255,255,255,.25); }
.pitch::after { content: ""; position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%); width: 120px; height: 120px; border: 1.5px solid rgba(255,255,255,.25); border-radius: 50%; }
.p-row { display: flex; justify-content: space-around; gap: 8px; z-index: 1; flex-wrap: wrap; }
.p-cell { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 5px 4px 4px; width: 82px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
.p-cell.cap { border-color: #37003c; box-shadow: 0 0 8px rgba(55,0,60,.3); }
.p-cell img { width: 38px; height: 48px; object-fit: contain; }
.p-cell .n { font-size: .66rem; font-weight: 600; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.p-cell .x { font-size: .74rem; font-weight: 600; color: #37003c; }
.p-cell .k { font-size: .56rem; color: #ea580c; font-weight: 600; letter-spacing: 1px; }

.news-warn { background: #fff1f2; border: 1px solid #fecdd3; color: #9f1239; border-radius: 8px; padding: 10px 14px; font-size: .8rem; font-weight: 400; }

/* ── FIXTURE TICKER COLORS (STRONG VIBRANT) ────────── */
.ftk-1, .ftk-2 { background: #01FC7A; color: #064420; }
.ftk-3 { background: #e2e8f0; color: #1e293b; }
.ftk-4 { background: #FF1751; color: #ffffff; }
.ftk-5 { background: #80072D; color: #ffffff; }
"""


def apply_theme():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def esc(s):
    return _html.escape(str(s))


import urllib.parse


def photo_url(code):
    c = str(code).split(".")[0]
    return f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{c}.png"


def jersey_svg_uri(team_short, pos=""):
    """Generate an inline vector SVG football kit data URI for a team."""
    bg, fg = JERSEY_COLORS.get(team_short, ("#37003c", "#ffffff"))
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 120" width="100" height="120">'
        f'<path d="M30 10 L8 36 L24 48 L24 112 L76 112 L76 48 L92 36 L70 10 C60 22 40 22 30 10 Z" fill="{bg}" stroke="{fg}" stroke-width="3.5"/>'
        f'<path d="M40 18 C45 23 55 23 60 18" stroke="{fg}" stroke-width="3" fill="none"/>'
        f'<text x="50" y="78" font-family="system-ui, -apple-system, sans-serif" font-size="24" font-weight="bold" fill="{fg}" text-anchor="middle">{pos}</text>'
        f'</svg>'
    )
    return f"data:image/svg+xml;utf8,{urllib.parse.quote(svg)}"


def player_img_html(p, cls="pc-img", style=""):
    """Render a player image as a <div> with CSS background-image layers.

    Photo is the top background layer; jersey SVG is the bottom fallback.
    If the photo 404s, the browser silently skips it and the jersey shows.
    Using <div> instead of <img> avoids broken-image icons entirely.
    """
    import re

    photo = p.get("photo_code") or ""
    team = p.get("team_short") or ""
    pos = p.get("pos") or ""
    fallback_uri = jersey_svg_uri(team, pos)

    cls_attr = f' class="{cls}"' if cls else ""

    if photo:
        url = photo_url(photo)
        bg = f"background-image:url('{url}'),url('{fallback_uri}');"
    else:
        bg = f"background-image:url('{fallback_uri}');"

    # Convert 'background:' shorthand to 'background-color:' so it doesn't
    # override our background-image. Match 'background:' but not 'background-*:'.
    safe_style = re.sub(r'(?<![-])background\s*:', 'background-color:', style)

    base_style = (
        f"display:inline-block;{bg}"
        f"background-size:contain;background-repeat:no-repeat;background-position:center;"
    )
    return f'<div{cls_attr} style="{base_style}{safe_style}"></div>'


def jersey_div(team_short, pos=""):
    """Render a colored jersey/shirt div for a team."""
    colors = JERSEY_COLORS.get(team_short, ("#64748b", "#fff"))
    bg, fg = colors
    border = f"border: 1.5px solid {fg};" if bg == "#fff" else ""
    return (
        f'<div class="pc-jersey" style="background:{bg};color:{fg};{border}">'
        f'{pos}</div>'
    )


def fdr_badge_html(fdr):
    if fdr is None:
        return '<span class="fdr-badge fdr-3">-</span>'
    label = FDR_LABELS.get(fdr, fdr)
    return f'<span class="fdr-badge fdr-{fdr}" title="{esc(label)}">{label}</span>'


def pos_badge_html(pos):
    return f'<span class="pos-badge pos-{pos}">{pos}</span>'


def status_badge_html(status):
    label = STATUS_LABELS.get(status, status)
    color = "#ffffff"
    bg = "#16a34a" if status == "a" else "#dc2626"
    return f'<span class="fdr-badge" style="background:{bg};color:{color}">{esc(label)}</span>'


def player_card_html(p, tag=None):
    parts = []
    if tag:
        cls = {"KAPTEN": "", "WAKIL": " vice", "ALT": " alt"}.get(tag, " alt")
        parts.append(f'<div class="tag{cls}">{esc(tag)}</div>')
    img = player_img_html(p, style="width:62px;height:78px;object-fit:contain;border-radius:6px;background:#f8fafc;")
    fixture = ""
    if p.get("opponent_short"):
        home = "Kandang" if p.get("is_home") else "Tandang"
        fixture = f'<div class="p-fixture">vs {esc(p["opponent_short"])} · {home} {fdr_badge_html(p.get("fdr"))}</div>'
    chance = ""
    if p.get("chance") is not None:
        chance = f'<div class="p-sub">Peluang main {float(p["chance"])*100:.0f}%</div>'
    proj = f'{p["proj"]:.2f}' if p["proj"] is not None else "-"
    return (
        f'<div class="p-card">{"".join(parts)}{img}'
        f'<div class="p-name">{esc(p["web_name"])}</div>'
        f'<div class="p-team">{esc(p["team_short"])} {pos_badge_html(p["pos"])}</div>'
        f'<div class="p-proj">{proj}</div>{fixture}{chance}</div>'
    )


def pitch_card_html(p, gw_projs=None, gd=None, is_captain=False, is_vice=False):
    """Render a player card on the pitch with 3 GW mini-projections and robust fallback."""
    img = player_img_html(p, cls="pc-img")
    cap_badge = '<div class="pc-cap">C</div>' if is_captain else ('<div class="pc-vice">V</div>' if is_vice else "")
    cap_cls = " captain" if is_captain else ""

    # GW mini-projection cells
    gw_html = ""
    if gw_projs and gd:
        pid = p.get("id")
        projs = gw_projs.get(pid, [0.0, 0.0, 0.0])
        cur = gd.next_event["id"]
        cells = []
        for i, val in enumerate(projs[:3]):
            gw_id = cur + i
            # Get opponent info for this GW
            team = p.get("team")
            fx = gd.fixture_for_team_event(team, gw_id) if team else None
            if fx:
                opp_short = gd.teams_by_id.get(fx["opponent"], {}).get("short_name", "?")
                ha = "K" if fx["is_home"] else "T"
                fdr = fx.get("difficulty", 3)
            else:
                opp_short = "-"
                ha = ""
                fdr = 3
            bg, fg = FDR_CELL.get(fdr, ("#f1f5f9", "#475569"))
            cells.append(
                f'<div class="gw-cell" style="background:{bg};color:{fg}">'
                f'<div class="gv">{val:.1f}</div>'
                f'<div class="gl">{opp_short}({ha})</div></div>'
            )
        gw_html = f'<div class="gw-cells">{"".join(cells)}</div>'

    team_short = esc(p.get("team_short", ""))
    return (
        f'<div class="pc{cap_cls}">{cap_badge}{img}'
        f'<div class="pc-name">{esc(p.get("web_name", "?"))}</div>'
        f'<div class="pc-team">{team_short}</div>'
        f'<div class="pc-price">{fmt_price(p.get("price", 0))}</div>'
        f'{gw_html}</div>'
    )


def stat_header_html(squad, ev, bank, total_proj):
    """Render the stat header bar with modern clean typography."""
    n = len(squad)
    total_val = sum(p.get("price", 0) for p in squad) / 10
    gw_id = ev.get("id", "?")
    deadline = fmt_deadline_wib(ev.get("deadline_time", ""), format_type="short")
    return (
        f'<div class="stat-bar">'
        f'<div class="stat-item"><div class="sv">GW {gw_id}</div><div class="sl">Gameweek</div></div>'
        f'<div class="stat-item"><div class="sv">{deadline}</div><div class="sl">Deadline (WIB)</div></div>'
        f'<div class="stat-item"><div class="sv">{total_proj:.1f} pts</div><div class="sl">Predicted</div></div>'
        f'<div class="stat-item"><div class="sv">£{bank:.1f}m</div><div class="sl">Bank</div></div>'
        f'<div class="stat-item"><div class="sv">£{total_val:.1f}m</div><div class="sl">Team Value</div></div>'
        f'<div class="stat-item"><div class="sv">{n}/15</div><div class="sl">Squad</div></div>'
        f'</div>'
    )


def bar(label, value, maxv, color):
    pct = min(100, value / maxv * 100) if maxv else 0
    return (
        f'<div class="bar-row"><span class="bar-label">{esc(label)}</span>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>'
        f'<span class="bar-val">{value:.2f}</span></div>'
    )


def countdown_html(deadline_iso):
    if not deadline_iso:
        return '<div class="cd-box"><div class="num">-</div><div class="lab">Deadline</div></div>'
    deadline = datetime.fromisoformat(deadline_iso.replace("Z", "+00:00"))
    diff = deadline - datetime.now().astimezone()
    if diff.total_seconds() <= 0:
        return '<div class="cd-box"><div class="num">-</div><div class="lab">Deadline</div></div>'
    secs = int(diff.total_seconds())
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    return (
        f'<div class="countdown">'
        f'<div class="cd-box"><div class="num">{days}</div><div class="lab">Hari</div></div>'
        f'<div class="cd-box"><div class="num">{hours:02d}</div><div class="lab">Jam</div></div>'
        f'<div class="cd-box"><div class="num">{mins:02d}</div><div class="lab">Menit</div></div>'
        f'<div class="cd-box"><div class="num">{secs:02d}</div><div class="lab">Detik</div></div>'
        f'</div>'
    )


def last_updated():
    try:
        import json

        cache = json.loads(CACHE_FILE.read_text())
        ts = cache.get(f"{BASE_URL}/bootstrap-static/", {}).get("ts")
        if ts:
            return datetime.fromtimestamp(ts).strftime("%d %b %H:%M")
    except Exception:
        pass
    return "-"


def render_sidebar_team():
    """Render FPL connected team card and sync tool in the sidebar."""
    from .team import load_manager, sync_team

    st.sidebar.markdown("---")
    st.sidebar.markdown("<div style='font-size:0.75rem;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#37003c;margin-bottom:8px'>⚽ Tim FPL Terhubung</div>", unsafe_allow_html=True)

    mgr = load_manager()
    saved_id = mgr.get("team_id", "") if mgr else ""

    if mgr:
        chip_badge = ""
        if mgr.get("active_chip"):
            chip_name = {"bboost": "Bench Boost", "3xc": "Triple Captain", "freehit": "Free Hit", "wildcard": "Wildcard"}.get(mgr["active_chip"], mgr["active_chip"].upper())
            chip_badge = f"<div style='display:inline-block;background:#37003c;color:#00ff87;font-size:0.68rem;padding:2px 6px;border-radius:4px;font-weight:600;margin-top:4px'>Chip Aktif: {chip_name}</div>"

        st.sidebar.markdown(
            f"""
            <div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px;margin-bottom:10px'>
              <div style='font-weight:700;color:#0f172a;font-size:0.95rem'>{_html.escape(mgr.get('team_name', ''))}</div>
              <div style='color:#64748b;font-size:0.78rem'>Manajer: <b style='color:#1e293b'>{_html.escape(mgr.get('manager_name', ''))}</b></div>
              <div style='display:flex;justify-content:space-between;margin-top:8px;font-size:0.78rem'>
                <div>Total Poin: <b style='color:#37003c'>{mgr.get('summary_overall_points', 0)}</b></div>
                <div>Peringkat: <b style='color:#37003c'>#{mgr.get('summary_overall_rank', 0):,}</b></div>
              </div>
              <div style='display:flex;justify-content:space-between;margin-top:3px;font-size:0.78rem'>
                <div>Bank: <b style='color:#0f766e'>£{mgr.get('bank', 0.0):.1f}m</b></div>
                <div>Nilai: <b style='color:#0f766e'>£{mgr.get('team_value', 100.0):.1f}m</b></div>
              </div>
              {chip_badge}
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.sidebar.expander("Hubungkan / Ganti Team ID", expanded=mgr is None):
        team_id_input = st.text_input(
            "FPL Team ID",
            value=str(saved_id) if saved_id else "",
            placeholder="Contoh: 925693",
            key="sidebar_team_id_input",
            help="Temukan di URL halaman Points FPL Anda: fantasy.premierleague.com/entry/[ID]/event/1",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Tarik Skuad", use_container_width=True, key="btn_sync_sidebar"):
                if team_id_input.strip():
                    with st.spinner("Sinkronisasi data tim FPL..."):
                        ok, res, err = sync_team(team_id_input.strip(), force=True)
                        if ok:
                            st.cache_data.clear()
                            st.session_state.pop("squad", None)
                            for pos in ["GK", "DEF", "MID", "FWD"]:
                                st.session_state.pop(f"sel_{pos}", None)
                            st.success(f"Terhubung ke {res['team_name']}!")
                            st.rerun()
                        else:
                            st.error(err)
                else:
                    st.warning("Masukkan ID Tim terlebih dahulu.")
        with c2:
            if mgr and st.button("Refresh", use_container_width=True, key="btn_refresh_team_sidebar"):
                with st.spinner("Memperbarui..."):
                    ok, res, err = sync_team(saved_id, force=True)
                    if ok:
                        st.cache_data.clear()
                        st.session_state.pop("squad", None)
                        for pos in ["GK", "DEF", "MID", "FWD"]:
                            st.session_state.pop(f"sel_{pos}", None)
                        st.rerun()


def autorefresh():
    try:
        from streamlit_autorefresh import st_autorefresh
    except ImportError:
        render_sidebar_team()
        return

    render_sidebar_team()

    interval = st.sidebar.selectbox(
        "Auto-refresh data",
        options=[0, 5, 10, 15, 30],
        format_func=lambda m: "Mati" if m == 0 else f"Setiap {m} menit",
        key="auto_refresh_minutes",
        index=2,
    )
    st.sidebar.caption(
        "Halaman otomatis dimuat ulang agar data & proyeksi mengikuti Gameweek terbaru."
    )
    if interval > 0:
        st_autorefresh(interval=interval * 60_000, key="fpl_autorefresh")
