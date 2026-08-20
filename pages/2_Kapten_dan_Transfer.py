import streamlit as st

from fpl.optimizer import overpriced_players, projection_explanation, risk_players, value_picks
from fpl.ui import apply_theme, autorefresh, esc, load_data, player_card_html, pos_badge_html
from fpl.utils import fmt_price

st.set_page_config(page_title="Kapten & Transfer", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()

from fpl.paststats import attach, load as load_past

with st.spinner("Memuat statistik musim lalu..."):
    dfp = attach(df, load_past(gd))

st.markdown('<div class="section">Kapten & <em>Transfer</em></div>', unsafe_allow_html=True)
st.caption("Rekomendasi kapten, value picks, dan pemain berisiko untuk Gameweek ini.")

players = df.to_dict("records")
available = [p for p in players if p["proj"] and p["proj"] > 0]

st.markdown('<div class="section" style="margin-top:16px">Kandidat <em>Kapten</em> Terbaik</div>', unsafe_allow_html=True)
top5 = sorted(available, key=lambda p: p["proj"], reverse=True)[:5]
tags = ["KAPTEN", "WAKIL", "ALT", "ALT", "ALT"]
cols = st.columns(5)
for col, p, tag in zip(cols, top5, tags):
    with col:
        st.markdown(player_card_html(p, tag=tag), unsafe_allow_html=True)

st.markdown('<div class="section" style="font-size:.92rem">Detail <em>perhitungan</em></div>', unsafe_allow_html=True)
for p in top5[:3]:
    with st.expander(f"{p['web_name']} ({p['team_short']}) - proyeksi {p['proj']:.2f} poin"):
        st.code(projection_explanation(p))

st.markdown('<div class="section">Value <em>Picks</em> — Poin Proyeksi per £1 Juta</div>', unsafe_allow_html=True)
st.caption("Pemain murah dengan proyeksi tertinggi: paling efisien untuk budget Anda.")
vps = value_picks(available, n=40)
for pos in ("GK", "DEF", "MID", "FWD"):
    subset = [p for p in vps if p["pos"] == pos][:5]
    if not subset:
        continue
    with st.expander(f"{pos} — 5 value picks terbaik", expanded=(pos in ("MID", "FWD"))):
        for p in subset:
            st.markdown(
                f"<div class='info-line'>"
                f"<b style='color:#fff'>{esc(p['web_name'])}</b> ({esc(p['team_short'])}) · {fmt_price(p['price'])} · "
                f"proyeksi <b style='color:#00ff87'>{p['proj']:.2f}</b> · value <b style='color:#f59e0b'>{p['value']:.2f}</b> poin/£1jt"
                f"</div>",
                unsafe_allow_html=True,
            )

st.markdown('<div class="section">Pemain <em>Berisiko</em></div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    st.markdown('<div class="fpl-card"><h3>Cedera / Peluang Main Rendah</h3><div class="card-sub">Paling banyak dipegang manajer lain — waspadai!</div>', unsafe_allow_html=True)
    risky = risk_players(players)
    if risky:
        for p in risky[:8]:
            chance = p.get("chance")
            peluang = f"{float(chance):.0f}%" if chance is not None else "?"
            st.markdown(
                f"<div class='info-line'><span style='color:#f87171;font-weight:800'>{esc(p['web_name'])}</span> "
                f"({esc(p['team_short'])}) · {p['selected_by']:.1f}% kepemilikan · peluang main {peluang}</div>",
                unsafe_allow_html=True,
            )
            if p["news"]:
                st.caption(p["news"])
    else:
        st.info("Tidak ada pemain berisiko terdeteksi.")
    st.markdown("</div>", unsafe_allow_html=True)
with c2:
    st.markdown('<div class="fpl-card"><h3>Mahal tapi Proyeksi Rendah</h3><div class="card-sub">Harga tinggi, ekspektasi poin GW ini rendah.</div>', unsafe_allow_html=True)
    over = overpriced_players(players)
    if over:
        for p in over[:8]:
            st.markdown(
                f"<div class='info-line'><span style='color:#fbbf24;font-weight:800'>{esc(p['web_name'])}</span> "
                f"({esc(p['team_short'])}) · {fmt_price(p['price'])} · proyeksi hanya {p['proj']:.2f}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("Tidak ada pemain yang mencolok.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="section">Acuan <em>Musim Lalu</em> (2025/26)</div>', unsafe_allow_html=True)
st.caption("Pemain dengan poin tertinggi musim lalu sebagai acuan — dipasangkan dengan proyeksi GW ini dan harga sekarang.")
with st.expander("Top 10 poin musim lalu + proyeksi sekarang", expanded=True):
    stars = dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0)].nlargest(10, "last_points")
    for p in stars.to_dict("records"):
        double = " · <b style='color:#00ff87'>DOUBLE SIGNAL</b>" if p["proj"] and p["proj"] >= 2.2 else ""
        st.markdown(
            f"<div class='info-line'><b style='color:#f59e0b'>{int(p['last_points'])} pts</b> — "
            f"<b style='color:#fff'>{esc(p['web_name'])}</b> ({esc(p['team_short'])}, {p['pos']}, {fmt_price(p['price'])}) · "
            f"ppg lalu {p['last_ppg']:.2f} · proyeksi GW ini <b style='color:#00ff87'>{p['proj']:.2f}</b>{double}</div>",
            unsafe_allow_html=True,
        )
with st.expander("Value musim lalu (poin per £1 juta, harga ≤ £11.0m)"):
    vals = dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0) & (dfp["price"] <= 110)].nlargest(8, "last_value")
    for p in vals.to_dict("records"):
        st.markdown(
            f"<div class='info-line'><b style='color:#00ff87'>{p['last_value']:.2f}</b> pts/£1jt — "
            f"<b style='color:#fff'>{esc(p['web_name'])}</b> ({esc(p['team_short'])}, {p['pos']}, {fmt_price(p['price'])}) · "
            f"{int(p['last_points'])} pts musim lalu · proyeksi GW ini <b style='color:#4ade80'>{p['proj']:.2f}</b></div>",
            unsafe_allow_html=True,
        )

st.divider()
st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem'>"
    "Statistik musim lalu hanya acuan — musim baru bisa berubah (tim baru, taktik, umur). "
    "Gabungkan dengan proyeksi GW ini untuk keputusan terbaik.</p>",
    unsafe_allow_html=True,
)
