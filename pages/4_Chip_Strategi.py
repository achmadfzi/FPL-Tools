import json

import pandas as pd
import streamlit as st

from fpl.api import DATA_DIR
from fpl.strategy import (
    bb_estimate,
    bench_players,
    best_player_per_team,
    calendar,
    gw_summary,
    squad_from_ids,
    tc_estimate,
)
from fpl.ui import apply_theme, autorefresh, esc, load_data, player_card_html
from fpl.utils import fmt_price

st.set_page_config(page_title="Chip Strategi", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event
bpt = best_player_per_team(df)

st.markdown('<div class="section">Chip <em>Strategi</em></div>', unsafe_allow_html=True)
st.caption(
    "Kapan waktu terbaik menggunakan Triple Captain (TC) dan Bench Boost (BB), "
    "berbasis jadwal Double Gameweek (DGW), Blank GW, dan proyeksi poin."
)

with st.expander("Aturan chip yang perlu diketahui"):
    st.markdown(
        """
        - **Triple Captain (TC)**: poin kapten dikali 3 (bukan 2). Bisa dipakai 1x per musim.
        - **Bench Boost (BB)**: poin 4 pemain cadangan ikut dihitung. Bisa dipakai 1x per musim.
        - TC dan BB **tidak bisa** dipakai bersamaan di Gameweek yang sama.
        - Chip tidak bisa dipakai setelah deadline GW berjalan.
        - **Double Gameweek (DGW)**: tim bermain 2 laga dalam 1 GW — kunci utama strategi TC & BB.
        - **Blank GW (BGW)**: tim tidak bertanding — hindari chip di GW ini.
        """
    )

squad_ids = []
if DATA_DIR.joinpath("squad.json").exists():
    try:
        squad_ids = json.loads(DATA_DIR.joinpath("squad.json").read_text())
    except (json.JSONDecodeError, OSError):
        squad_ids = []
squad = squad_from_ids(df, squad_ids)
has_squad = len(squad) == 15

cal = calendar(gd, max_gws=12)

with st.expander("Kalender DGW / Blank GW (jadwal penuh musim ini)"):
    if all(not g["dgw_ids"] and not g["bgw_ids"] for g in cal):
        st.info("Tidak ada Double Gameweek atau Blank GW terdeteksi di 12 Gameweek ke depan.")
    for g in cal:
        if g["dgw_ids"] or g["bgw_ids"]:
            dgw = ", ".join(gd.teams_by_id[t]["short_name"] for t in g["dgw_ids"])
            bgw = ", ".join(gd.teams_by_id[t]["short_name"] for t in g["bgw_ids"])
            st.write(f"GW {g['event']}: DGW = {dgw or '-'} | BGW = {bgw or '-'}")

st.markdown('<div class="section">Skor <em>Kelayakan</em> Chip per Gameweek</div>', unsafe_allow_html=True)

rows = []
for g in cal:
    tc = tc_estimate(g, bpt)
    bb = bb_estimate(g, squad)
    deadline = next((e["deadline_time"][:10] for e in gd.events if e["id"] == g["event"]), "-")
    rows.append(
        {
            "GW": g["event"],
            "Deadline": deadline,
            "DGW": len(g["dgw_ids"]),
            "BGW": len(g["bgw_ids"]),
            "Laga Mudah": g["easy"],
            "Laga Sulit": g["hard"],
            "TC": tc["score"] if tc else None,
            "BB": bb["score"] if bb else None,
        }
    )
cal_df = pd.DataFrame(rows)

style_map = "background-color:#14532d;color:#fff;font-weight:800;text-align:center"


def highlight_max(s):
    m = s.max()
    return [style_map if (v == m and pd.notna(v)) else "" for v in s]


styled_cal = (
    cal_df.style.map(lambda v: "color:#8b93a7" if pd.isna(v) else "", subset=["TC", "BB"])
    .apply(highlight_max, subset=["TC"])
    .apply(highlight_max, subset=["BB"])
    .map(lambda v: "color:#4ade80;font-weight:800", subset=["Laga Mudah"])
    .map(lambda v: "color:#f87171;font-weight:800", subset=["Laga Sulit"])
    .format({"TC": "{:.2f}", "BB": "{:.2f}"})
    .hide(axis="index")
)
st.dataframe(styled_cal, use_container_width=True)
st.caption(
    "TC skor = estimasi poin kapten terbaik di GW itu (x1.9 bila timnya DGW). "
    "BB skor = estimasi poin 4 pemain cadangan (x1.8 bila DGW). Nilai hijau = GW terbaik."
)

st.divider()

c1, c2 = st.columns(2)

with c1:
    st.markdown('<div class="section" style="font-size:1rem">Triple <em>Captain</em></div>', unsafe_allow_html=True)
    tc_now = tc_estimate(gw_summary(gd, ev["id"]), bpt)
    st.markdown(
        f"""
        <div class="fpl-card">
          <h3>Kapan TC paling bernilai?</h3>
          <div class="card-sub">TC memberi tambahan 1x poin kapten (3x vs 2x normal). Gunakan saat:</div>
          <div class="info-line">1. Kapten terbaik Anda punya <b>lawan sangat mudah (FDR 1-2)</b> di kandang.</div>
          <div class="info-line">2. Tim kapten Anda <b>main 2 laga (DGW)</b> di GW itu.</div>
          <div class="info-line">3. Proyeksi kapten jauh di atas rata-rata GW lain.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    top5 = df.dropna(subset=["proj"]).sort_values("proj", ascending=False).head(5)
    cards = st.columns(3)
    for col, (_, p) in zip(cards, top5.head(3).iterrows()):
        with col:
            st.markdown(player_card_html(p, tag="TC +" + f"{p['proj']:.2f}"), unsafe_allow_html=True)
    st.caption(f"GW ini (GW {ev['id']}): TC memberi tambahan ±{tc_now['score']:.2f} poin vs kapten normal.")

    tc_rows = []
    for g in cal:
        t = tc_estimate(g, bpt)
        if t:
            tc_rows.append(
                {
                    "GW": g["event"],
                    "Laga Mudah": g["easy"],
                    "Kapten (est)": f"{t['player']} ({t['team_short']})",
                    "Proyeksi": t["proj"],
                    "TC Skor": t["score"],
                }
            )
    if tc_rows:
        tc_df = pd.DataFrame(tc_rows).sort_values("TC Skor", ascending=False).head(5)
        best_tc = tc_df.iloc[0]
        st.markdown(
            f'<div class="section" style="font-size:.95rem">GW terbaik untuk <em>TC</em></div>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            tc_df.style.apply(highlight_max, subset=["TC Skor"]).format({"Proyeksi": "{:.2f}", "TC Skor": "{:.2f}"}).hide(axis="index"),
            use_container_width=True,
            hide_index=True,
        )
        alasan = f"{best_tc['Laga Mudah']} laga mudah di GW itu"
        st.success(
            f"Rekomendasi: gunakan TC di **GW {int(best_tc['GW'])}** — kapten terbaik proyeksi "
            f"{best_tc['Proyeksi']:.2f} ({alasan}). Bonus TC ±{best_tc['TC Skor']:.2f} poin."
            + (" **GW ini berjalan — pasang sebelum deadline!**" if int(best_tc["GW"]) == ev["id"] else "")
        )

with c2:
    st.markdown('<div class="section" style="font-size:1rem">Bench <em>Boost</em></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="fpl-card">
          <h3>Kapan BB paling bernilai?</h3>
          <div class="card-sub">BB menjadikan 4 cadangan ikut memberi poin. Gunakan saat:</div>
          <div class="info-line">1. <b>Cadangan Anda kuat</b> (proyeksi 4 terendah &ge; ±8 poin).</div>
          <div class="info-line">2. Banyak pemain tim Anda <b>main 2 laga (DGW)</b>.</div>
          <div class="info-line">3. Semua pemain <b>bebas cedera/suspensi</b>.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if has_squad:
        bench = bench_players(squad)
        bb_now = bb_estimate(gw_summary(gd, ev["id"]), squad)
        st.markdown(
            f"<div class='info-line'>Nilai cadangan GW ini: <b style='color:#00ff87'>{bb_now['score']:.2f}</b> poin.</div>",
            unsafe_allow_html=True,
        )
        bench_html = '<div class="bench-row">'
        for p in bench:
            bench_html += (
                f'<div class="bench-cell"><div><div class="n">{esc(p["web_name"])} ({esc(p["team_short"])})</div>'
                f'<div class="x">{p["proj"]:.2f} poin</div></div></div>'
            )
        bench_html += "</div>"
        st.markdown(bench_html, unsafe_allow_html=True)
        bb_now_val = bb_now["score"]
        verdict = (
            "Cadangan Anda sudah cukup kuat — pertimbangkan BB di GW ini."
            if bb_now_val >= 8.0
            else "Cadangan masih tipis — tunggu GW dengan skor BB lebih tinggi."
        )
        st.caption(verdict)

        bb_rows = []
        for g in cal:
            b = bb_estimate(g, squad)
            if b:
                bb_rows.append({"GW": g["event"], "Laga Mudah": g["easy"], "Pemain DGW": b["dgw_count"], "BB Skor": b["score"]})
        if bb_rows:
            bb_df = pd.DataFrame(bb_rows).sort_values("BB Skor", ascending=False).head(5)
            st.markdown('<div class="section" style="font-size:.95rem">GW terbaik untuk <em>BB</em></div>', unsafe_allow_html=True)
            st.dataframe(
                bb_df.style.apply(highlight_max, subset=["BB Skor"]).format({"BB Skor": "{:.2f}"}).hide(axis="index"),
                use_container_width=True,
            )
            best_bb = bb_df.iloc[0]
            st.success(
                f"Rekomendasi: gunakan BB di **GW {int(best_bb['GW'])}** — estimasi cadangan "
                f"{best_bb['BB Skor']:.2f} poin ({int(best_bb['Pemain DGW'])} pemain DGW)."
                + (" **GW ini berjalan — pasang sebelum deadline!**" if int(best_bb["GW"]) == ev["id"] else "")
            )
    else:
        st.info(
            "Simpan skuad 15 pemain dulu (Team Builder > Simpan Tim, atau jalankan `python recommend.py`) "
            "agar analisis BB bisa dihitung dari skuad Anda."
        )

st.divider()
st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem'>"
    "Estimasi GW mendatang memakai proyeksi pemain saat ini sebagai patokan (data per pemain per GW "
    "baru tersedia saat GW berjalan). Pantau ulang setiap menjelang deadline.</p>",
    unsafe_allow_html=True,
)
