import html as _html
from datetime import datetime

import streamlit as st

from .api import CACHE_FILE, BASE_URL, get_game_data
from .model import build_projection_table
from .utils import FDR_LABELS, STATUS_LABELS


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

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
  font-family: 'Inter', system-ui, sans-serif;
  color: #e7e9ee;
}
[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1.2rem; max-width: 1320px; }
h1, h2, h3 { color: #ffffff !important; letter-spacing: -0.02em; }
.stApp [data-testid="stSidebar"] { background: #10141d; border-right: 1px solid #232b3b; }

.fpl-hero {
  background: linear-gradient(120deg, #1b0b2e 0%, #3b1470 55%, #0e7a3d 140%);
  border-radius: 18px; padding: 24px 30px 20px; margin-bottom: 18px;
  border: 1px solid rgba(255,255,255,.08);
}
.fpl-hero .kicker { letter-spacing: 3px; text-transform: uppercase; font-size: .7rem; color: #00ff87; font-weight: 800; }
.fpl-hero h1 { font-size: 2rem; font-weight: 900; margin: 4px 0 6px; color: #fff !important; }
.fpl-hero .sub { color: #c9b8e8; font-size: .92rem; margin: 0; }
.fpl-hero .updated { color: #8b93a7; font-size: .74rem; margin-top: 8px; }

.countdown { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
.cd-box { background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.22); border-radius: 12px; padding: 8px 16px; text-align: center; min-width: 74px; }
.cd-box .num { font-size: 1.45rem; font-weight: 800; color: #fff; line-height: 1.2; }
.cd-box .lab { font-size: .6rem; text-transform: uppercase; letter-spacing: 1.5px; color: #b9a8d8; }

.fpl-card { background: #161b27; border: 1px solid #232b3b; border-radius: 14px; padding: 16px 18px; }
.fpl-card h3 { margin: 0 0 8px; font-size: 1rem; font-weight: 800; }
.fpl-card .card-sub { color: #8b93a7; font-size: .78rem; margin-bottom: 10px; }

.p-card {
  background: #161b27; border: 1px solid #232b3b; border-radius: 14px;
  padding: 16px 12px 12px; text-align: center; position: relative; height: 100%;
}
.p-card img { width: 66px; height: 82px; object-fit: contain; border-radius: 10px; background: #0d1117; }
.p-card .p-name { font-weight: 800; font-size: .9rem; margin-top: 8px; color: #fff; }
.p-card .p-team { font-size: .68rem; color: #8b93a7; text-transform: uppercase; letter-spacing: .5px; margin-top: 2px; }
.p-card .p-proj { font-size: 1.3rem; font-weight: 900; color: #00ff87; margin-top: 6px; }
.p-card .p-fixture { font-size: .68rem; color: #c2c8d6; margin-top: 4px; }
.p-card .p-sub { font-size: .64rem; color: #8b93a7; margin-top: 3px; }
.p-card .tag {
  position: absolute; top: -11px; left: 50%; transform: translateX(-50%);
  background: #00ff87; color: #052e16; font-weight: 900; font-size: .62rem;
  letter-spacing: 1px; padding: 3px 12px; border-radius: 99px; white-space: nowrap;
}
.p-card .tag.vice { background: #f59e0b; color: #451a03; }
.p-card .tag.alt { background: #7c3aed; color: #fff; }

.fdr-badge { display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: .64rem; font-weight: 800; color: #fff; }
.fdr-1 { background: #16a34a; }
.fdr-2 { background: #4ade80; color: #052e16; }
.fdr-3 { background: #52525b; }
.fdr-4 { background: #f59e0b; color: #451a03; }
.fdr-5 { background: #dc2626; }

.pos-badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: .62rem; font-weight: 800; color: #fff; }
.pos-GK { background: #ca8a04; }
.pos-DEF { background: #2563eb; }
.pos-MID { background: #16a34a; }
.pos-FWD { background: #dc2626; }

.bar-row { display: flex; align-items: center; gap: 8px; margin: 6px 0; font-size: .72rem; }
.bar-label { width: 160px; color: #8b93a7; text-align: right; flex-shrink: 0; }
.bar-track { flex: 1; background: #0d1117; border-radius: 99px; height: 9px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 99px; }
.bar-val { width: 46px; color: #e7e9ee; font-weight: 700; flex-shrink: 0; }

[data-testid="stMetric"] { background: #161b27; border: 1px solid #232b3b; border-radius: 14px; padding: 12px 16px; }
[data-testid="stMetric"] label { color: #8b93a7; }
[data-testid="stMetricValue"] { color: #fff; }

.stExpander { background: #161b27 !important; border: 1px solid #232b3b !important; border-radius: 12px !important; }
[data-testid="stExpanderDetails"] { background: #161b27 !important; }

.section { margin: 26px 0 12px; font-size: 1.08rem; font-weight: 900; color: #fff; letter-spacing: .3px; }
.section em { color: #00ff87; font-style: normal; }

.pitch {
  position: relative;
  background: repeating-linear-gradient(90deg, #157a3d 0 76px, #116b34 76px 152px);
  border-radius: 16px; padding: 18px 12px; border: 3px solid rgba(255,255,255,.15);
  display: flex; flex-direction: column; gap: 18px;
}
.pitch::before { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; background: rgba(255,255,255,.25); }
.pitch::after { content: ""; position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%); width: 170px; height: 170px; border: 2px solid rgba(255,255,255,.25); border-radius: 50%; }
.p-row { display: flex; justify-content: space-around; gap: 8px; z-index: 1; flex-wrap: wrap; }
.p-cell { background: rgba(13,17,23,.88); border: 1px solid #2a3040; border-radius: 10px; padding: 6px 5px 5px; width: 82px; text-align: center; }
.p-cell.cap { border-color: #00ff87; box-shadow: 0 0 12px rgba(0,255,135,.35); }
.p-cell img { width: 38px; height: 48px; object-fit: contain; }
.p-cell .n { font-size: .66rem; font-weight: 800; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.p-cell .x { font-size: .74rem; font-weight: 900; color: #00ff87; }
.p-cell .k { font-size: .56rem; color: #f59e0b; font-weight: 900; letter-spacing: 1px; }

.bench-row { display: flex; gap: 10px; flex-wrap: wrap; }
.bench-cell { background: #161b27; border: 1px solid #232b3b; border-radius: 10px; padding: 8px 12px; display: flex; align-items: center; gap: 8px; }
.bench-cell img { width: 24px; height: 30px; object-fit: contain; }
.bench-cell .n { font-size: .74rem; font-weight: 700; color: #fff; }
.bench-cell .x { font-size: .7rem; font-weight: 800; color: #8b93a7; }

.news-warn { background: #2d1518; border: 1px solid #7f1d1d; color: #fca5a5; border-radius: 10px; padding: 10px 14px; font-size: .82rem; }

.info-line { color: #c2c8d6; font-size: .82rem; margin: 2px 0; }
.info-line b { color: #fff; }

[data-testid="stButton"] button {
  background: #3b1470; border: 1px solid #5b21b6; color: #fff; border-radius: 10px; font-weight: 700;
}
[data-testid="stButton"] button:hover { border-color: #00ff87; color: #fff; }
[data-testid="stButton"] button:disabled { background: #232b3b; border-color: #2a3040; color: #8b93a7; }

[data-testid="stDataFrame"] { border: 1px solid #232b3b; border-radius: 12px; overflow: hidden; }
"""


def apply_theme():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def esc(s):
    return _html.escape(str(s))


def photo_url(code):
    c = str(code).split(".")[0]
    return f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{c}.png"


def fdr_badge_html(fdr):
    if fdr is None:
        return '<span class="fdr-badge fdr-3">-</span>'
    label = FDR_LABELS.get(fdr, fdr)
    return f'<span class="fdr-badge fdr-{fdr}" title="{esc(label)}">{label}</span>'


def pos_badge_html(pos):
    return f'<span class="pos-badge pos-{pos}">{pos}</span>'


def status_badge_html(status):
    label = STATUS_LABELS.get(status, status)
    color = "#16a34a" if status == "a" else "#dc2626"
    return f'<span class="fdr-badge" style="background:{color}">{esc(label)}</span>'


def player_card_html(p, tag=None):
    parts = []
    if tag:
        cls = {"KAPTEN": "", "WAKIL": " vice", "ALT": " alt"}.get(tag, " alt")
        parts.append(f'<div class="tag{cls}">{esc(tag)}</div>')
    img = f'<img src="{photo_url(p["photo_code"])}" loading="lazy">' if p.get("photo_code") else '<img src="" style="visibility:hidden">'
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


def autorefresh():
    try:
        from streamlit_autorefresh import st_autorefresh
    except ImportError:
        return
    interval = st.sidebar.selectbox(
        "Auto-refresh data",
        options=[0, 5, 10, 15, 30],
        format_func=lambda m: "Mati" if m == 0 else f"Setiap {m} menit",
        key="auto_refresh_minutes",
        index=2,
    )
    st.sidebar.caption(
        "Halaman otomatis dimuat ulang agar data & proyeksi mengikuti Gameweek terbaru "
        "(pergantian GW terdeteksi otomatis dari API FPL)."
    )
    if interval > 0:
        st_autorefresh(interval=interval * 60_000, key="fpl_autorefresh")
