import streamlit as st

from fpl.optimizer import projection_explanation
from fpl.ui import (
    apply_theme,
    autorefresh,
    countdown_html,
    esc,
    fdr_badge_html,
    last_updated,
    load_data,
    photo_url,
    player_card_html,
    pos_badge_html,
    refresh,
)
from fpl.utils import fmt_price

st.set_page_config(page_title="FPL Dashboard - Beranda", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event

st.markdown(
    f"""
    <div class="fpl-hero">
      <div class="kicker">Fantasy Premier League · Toolkit</div>
      <h1>FPL Dashboard</h1>
      <div class="sub">Rekomendasi kapten, transfer, dan line-up berbasis data untuk Gameweek {ev.get('id')}.</div>
      <div class="updated">Data terakhir diperbarui: {last_updated()} | Deadline GW {ev.get('id')}: {ev.get('deadline_time', '')[:16].replace('T', ' ')}</div>
      {countdown_html(ev.get('deadline_time'))}
    </div>
    """,
    unsafe_allow_html=True,
)

c_refresh, c_spacer = st.columns([1, 5])
with c_refresh:
    if st.button("Segarkan Data", use_container_width=True):
        refresh()
with c_spacer:
    st.caption(
        "Deadline FPL selalu beberapa jam sebelum kickoff pertama. "
        "Dashboard **otomatis mengikuti pergantian Gameweek** — saat deadline lewat dan API FPL pindah ke GW berikutnya, "
        "seluruh data, proyeksi, kapten, dan FDR langsung menyesuaikan."
    )

c1, c2, c3, c4 = st.columns(4)
top_cap = df.dropna(subset=["proj"]).sort_values("proj", ascending=False).iloc[0]
c1.metric("Gameweek", f"GW {ev.get('id')}")
c2.metric("Total pemain", f"{len(df)}")
c3.metric("Pertandingan GW depan", f"{len(gd.fixtures_by_team) // 2} laga")
c4.metric("Kapten rekomendasi", f"{top_cap['web_name']} ({top_cap['proj']:.2f} pts)")

st.markdown('<div class="section">Rekomendasi <em>Kapten</em></div>', unsafe_allow_html=True)
top3 = df.dropna(subset=["proj"]).sort_values("proj", ascending=False).head(3)
cards = st.columns(3)
tags = ["KAPTEN", "WAKIL", "ALT"]
for col, (_, row), tag in zip(cards, top3.iterrows(), tags):
    with col:
        st.markdown(player_card_html(row, tag=tag), unsafe_allow_html=True)

st.markdown('<div class="section">Alasan <em>di balik</em> pilihan kapten</div>', unsafe_allow_html=True)
for i, (_, row) in enumerate(top3.iterrows(), 1):
    label = "Kapten" if i == 1 else ("Wakil Kapten" if i == 2 else f"Alternatif {i}")
    with st.expander(f"{label}: {row['web_name']} ({row['team_short']})"):
        st.code(projection_explanation(row))

st.markdown('<div class="section">Tingkat Kesulitan Lawan <em>(FDR)</em> GW Depan</div>', unsafe_allow_html=True)
teams_fdr = []
for t in gd.teams_by_id.values():
    fx = gd.fixture_for_team(t["id"])
    teams_fdr.append(
        {
            "tim": t["short_name"],
            "lawan": gd.teams_by_id[fx["opponent"]]["short_name"] if fx else "-",
            "fdr": fx["difficulty"] if fx else None,
            "home": "Kandang" if fx and fx["is_home"] else ("Tandang" if fx else "-"),
        }
    )
teams_fdr.sort(key=lambda x: (x["fdr"] is None, x["fdr"] or 9))
fdr_html = '<div class="fpl-card"><div class="bench-row">'
for t in teams_fdr:
    fdr_html += (
        f'<div class="bench-cell"><span class="n">{esc(t["tim"])}</span>'
        f'<span class="x">{esc(t["lawan"])} · {esc(t["home"])} {fdr_badge_html(t["fdr"])}</span></div>'
    )
fdr_html += "</div></div>"

st.markdown(fdr_html, unsafe_allow_html=True)

st.markdown('<div class="section">Top 10 <em>Proyeksi Poin</em> Gameweek Ini</div>', unsafe_allow_html=True)
top = df.dropna(subset=["proj"]).sort_values("proj", ascending=False).head(10)
rows = "<div class='fpl-card'><div style='display:flex;flex-direction:column;gap:8px'>"
for rank, (_, p) in enumerate(top.iterrows(), 1):
    home = "Kandang" if p.get("is_home") else "Tandang"
    rows += (
        f'<div style="display:flex;align-items:center;gap:12px">'
        f'<span style="width:24px;font-weight:900;color:#8b93a7">{rank}</span>'
        f'<img src="{photo_url(p["photo_code"])}" style="width:34px;height:42px;object-fit:contain;background:#0d1117;border-radius:6px">'
        f'<span style="font-weight:700;color:#fff;min-width:150px">{esc(p["web_name"])}</span>'
        f'<span style="min-width:60px">{pos_badge_html(p["pos"])}</span>'
        f'<span style="color:#8b93a7;min-width:70px">{esc(p["team_short"])}</span>'
        f'<span style="color:#8b93a7;min-width:60px">{fmt_price(p["price"])}</span>'
        f'<span style="color:#8b93a7;flex:1">vs {esc(p["opponent_short"])} · {home}</span>'
        f'{fdr_badge_html(p.get("fdr"))}'
        f'<span style="font-weight:900;color:#00ff87;min-width:56px;text-align:right">{p["proj"]:.2f}</span>'
        f'</div>'
    )
rows += "</div></div>"

st.markdown(rows, unsafe_allow_html=True)

st.markdown('<div class="section">Pemain dengan <em>Lawan Mudah</em> (FDR 1-2)</div>', unsafe_allow_html=True)
easy = df.dropna(subset=["proj"]).query("fdr <= 2 and chance >= 75").sort_values("proj", ascending=False).head(12)
easy_cards = st.columns(4)
for col, (_, p) in zip(easy_cards, easy.head(4).iterrows()):
    with col:
        st.markdown(player_card_html(p), unsafe_allow_html=True)
if len(easy) > 4:
    st.caption(f"+ {len(easy) - 4} pemain lain dengan lawan mudah — lihat di Player Explorer.")

st.markdown('<div class="section">Bintang <em>Musim Lalu</em> — Acuan Musim Ini</div>', unsafe_allow_html=True)
st.caption(
    "Top poin musim lalu (2025/26) sebagai acuan, lengkap dengan proyeksi GW ini. "
    "Tanda <b style='color:#00ff87'>DOUBLE</b> = poin tinggi musim lalu DAN proyeksi tinggi sekarang."
)

from fpl.paststats import attach, indicator as past_indicator, load as load_past

with st.spinner("Memuat statistik musim lalu..."):
    dfp = attach(df, load_past(gd))
stars = dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0)].nlargest(10, "last_points")
rows = "<div class='fpl-card'><div style='display:flex;flex-direction:column;gap:8px'>"
for rank, (_, p) in enumerate(stars.iterrows(), 1):
    double = "<span class='fdr-badge fdr-2'>DOUBLE</span>" if p["proj"] and p["proj"] >= 2.2 else ""
    proj_txt = f"{p['proj']:.2f}" if p["proj"] is not None else "-"
    rows += (
        f'<div style="display:flex;align-items:center;gap:12px">'
        f'<span style="width:24px;font-weight:900;color:#8b93a7">{rank}</span>'
        f'<span style="font-weight:700;color:#fff;min-width:150px">{esc(p["web_name"])}</span>'
        f'<span style="min-width:56px">{pos_badge_html(p["pos"])}</span>'
        f'<span style="color:#8b93a7;min-width:56px">{esc(p["team_short"])}</span>'
        f'<span style="font-weight:900;color:#f59e0b;min-width:70px">{int(p["last_points"])} pts</span>'
        f'<span style="color:#8b93a7;min-width:60px">ppg {p["last_ppg"]:.2f}</span>'
        f'<span style="color:#8b93a7;min-width:60px">{fmt_price(p["price"])}</span>'
        f'<span style="color:#8b93a7;flex:1">proyeksi GW ini: <b style="color:#fff">{proj_txt}</b></span>'
        f'{double}</div>'
    )
rows += "</div></div>"
st.markdown(rows, unsafe_allow_html=True)

st.markdown('<div class="section" style="font-size:.95rem">Value <em>Musim Lalu</em> — Poin per £1 Juta</div>', unsafe_allow_html=True)
st.caption("Pemain murah yang mencetak banyak poin musim lalu — kandidat budget pick terbaik.")
vals = dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0) & (dfp["price"] <= 110)].nlargest(8, "last_value")
vrows = '<div class="fpl-card"><div style="display:flex;flex-direction:column;gap:8px">'
for rank, (_, p) in enumerate(vals.iterrows(), 1):
    vrows += (
        f'<div style="display:flex;align-items:center;gap:12px">'
        f'<span style="width:24px;font-weight:900;color:#8b93a7">{rank}</span>'
        f'<span style="font-weight:700;color:#fff;min-width:150px">{esc(p["web_name"])}</span>'
        f'<span style="min-width:56px">{pos_badge_html(p["pos"])}</span>'
        f'<span style="color:#8b93a7;min-width:56px">{esc(p["team_short"])}</span>'
        f'<span style="font-weight:900;color:#00ff87;min-width:90px">{p["last_value"]:.2f} pts/£1jt</span>'
        f'<span style="color:#f59e0b;min-width:70px">{int(p["last_points"])} pts</span>'
        f'<span style="color:#8b93a7;flex:1">{fmt_price(p["price"])} · proyeksi GW ini: <b style="color:#fff">{p["proj"]:.2f}</b></span>'
        f'</div>'
    )
vrows += "</div></div>"
st.markdown(vrows, unsafe_allow_html=True)

st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem;margin-top:24px'>"
    "Semua angka adalah estimasi berbasis statistik (form, FDR, kandang/tandang, proyeksi FPL). "
    "Keputusan akhir tetap di tangan Anda.</p>",
    unsafe_allow_html=True,
)
