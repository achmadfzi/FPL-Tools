import json

import pandas as pd
import streamlit as st

from fpl.api import DATA_DIR
from fpl.strategy import (
    bb_estimate,
    bench_players,
    best_player_per_team,
    calendar,
    chip_sequence,
    fh_estimate,
    gw_summary,
    squad_from_ids,
    tc_estimate,
    wc_estimate,
)
from fpl.ui import apply_theme, autorefresh, esc, load_data, player_card_html
from fpl.utils import fmt_deadline_wib, fmt_price

st.set_page_config(page_title="Chip Strategi", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event
bpt = best_player_per_team(df)

st.markdown('<div class="section">Chip <em>Strategi</em></div>', unsafe_allow_html=True)
st.caption(
    "Kapan waktu terbaik menggunakan Triple Captain (TC), Bench Boost (BB), "
    "Wildcard (WC), dan Free Hit (FH) — berbasis jadwal DGW, BGW, dan proyeksi poin."
)

with st.expander("Aturan chip yang perlu diketahui"):
    st.markdown(
        """
        - **Triple Captain (TC)**: poin kapten dikali 3 (bukan 2). Bisa dipakai 1x per musim.
        - **Bench Boost (BB)**: poin 4 pemain cadangan ikut dihitung. Bisa dipakai 1x per musim.
        - **Wildcard (WC)**: rebuild seluruh skuad 15 pemain tanpa penalti transfer. Bisa dipakai 2x per musim (1x per paruh).
        - **Free Hit (FH)**: rebuild tim untuk 1 GW saja, lalu kembali ke skuad semula. Bisa dipakai 1x per musim.
        - TC dan BB **tidak bisa** dipakai bersamaan di Gameweek yang sama.
        - **Double Gameweek (DGW)**: tim bermain 2 laga dalam 1 GW — kunci utama strategi TC & BB.
        - **Blank GW (BGW)**: tim tidak bertanding — kunci utama strategi FH.
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

# --- Skor Kelayakan Semua Chip ---
st.markdown('<div class="section">Skor <em>Kelayakan</em> Chip per Gameweek</div>', unsafe_allow_html=True)

rows = []
tc_all = []
bb_all = []
wc_all = []
fh_all = []

for g in cal:
    tc = tc_estimate(g, bpt)
    bb = bb_estimate(g, squad)
    wc = wc_estimate(g, gd, df, squad if has_squad else None)
    fh = fh_estimate(g, gd, df)
    deadline = next((fmt_deadline_wib(e["deadline_time"], format_type="short") for e in gd.events if e["id"] == g["event"]), "-")

    if tc:
        tc_all.append({"gw": g["event"], "score": tc["score"], "reason": f"Kapten: {tc['player']}"})
    if bb:
        bb_all.append({"gw": g["event"], "score": bb["score"], "reason": f"{bb['dgw_count']} pemain DGW"})
    if wc:
        wc_all.append({"gw": g["event"], "score": wc["score"], "reason": f"{wc['future_easy_fixtures']} laga mudah"})
    if fh:
        fh_all.append({"gw": g["event"], "score": fh["score"], "reason": f"{fh['n_blank_teams']} tim blank"})

    rows.append(
        {
            "GW": g["event"],
            "Deadline (WIB)": deadline,
            "DGW": len(g["dgw_ids"]),
            "BGW": len(g["bgw_ids"]),
            "Laga Mudah": g["easy"],
            "Laga Sulit": g["hard"],
            "TC": tc["score"] if tc else None,
            "BB": bb["score"] if bb else None,
            "WC": wc["score"] if wc else None,
            "FH": fh["score"] if fh else None,
        }
    )
cal_df = pd.DataFrame(rows)

style_map = "background-color:#37003c;color:#00ff87;font-weight:600;text-align:center"


def highlight_max(s):
    m = s.max()
    return [style_map if (v == m and pd.notna(v)) else "color:#0f172a;font-weight:400;text-align:center" for v in s]


styled_cal = (
    cal_df.style
    .map(lambda v: "color:#0f172a;font-weight:400;text-align:center", subset=["GW", "Deadline (WIB)", "DGW", "BGW"])
    .map(lambda v: "color:#94a3b8;text-align:center" if pd.isna(v) else "color:#0f172a;font-weight:400;text-align:center", subset=["TC", "BB", "WC", "FH"])
    .apply(highlight_max, subset=["TC"])
    .apply(highlight_max, subset=["BB"])
    .apply(highlight_max, subset=["WC"])
    .apply(highlight_max, subset=["FH"])
    .map(lambda v: "color:#16a34a;font-weight:600;text-align:center", subset=["Laga Mudah"])
    .map(lambda v: "color:#dc2626;font-weight:600;text-align:center", subset=["Laga Sulit"])
    .format({"TC": "{:.2f}", "BB": "{:.2f}", "WC": "{:.2f}", "FH": "{:.2f}"})
    .hide(axis="index")
)
st.dataframe(styled_cal, use_container_width=True, hide_index=True)
st.caption(
    "TC skor = estimasi poin kapten terbaik (×1.9 bila DGW). "
    "BB skor = estimasi poin 4 cadangan (×1.8 bila DGW). "
    "WC skor = value rebuild berdasarkan fixture swing + DGW. "
    "FH skor = value free hit berdasarkan jumlah tim blank. "
    "Kotak ungu = GW terbaik per chip."
)

# --- Chip Sequence Plan ---
st.markdown('<div class="section">Rencana <em>Chip</em> Musim Ini</div>', unsafe_allow_html=True)
st.caption("Urutan optimal penggunaan 4 chip berdasarkan jadwal dan proyeksi saat ini.")

plan = chip_sequence(cal, tc_all, bb_all, wc_all, fh_all)
if plan:
    chip_colors = {"TC": "#37003c", "BB": "#e85d04", "WC": "#6a0dad", "FH": "#2f80ed"}
    chip_names = {"TC": "Triple Captain", "BB": "Bench Boost", "WC": "Wildcard", "FH": "Free Hit"}
    plan_html = '<div class="fpl-card"><div style="display:flex;gap:16px;flex-wrap:wrap">'
    for p in plan:
        color = chip_colors.get(p["chip"], "#8b93a7")
        plan_html += (
            f'<div style="background:#fff;border:2px solid {color};border-radius:14px;padding:14px 20px;text-align:center;min-width:140px;box-shadow:0 2px 8px rgba(0,0,0,.08)">'
            f'<div style="font-size:.7rem;color:{color};font-weight:900;letter-spacing:2px">{chip_names.get(p["chip"], p["chip"])}</div>'
            f'<div style="font-size:1.6rem;font-weight:900;color:#1a1a2e;margin:4px 0">GW {p["gw"]}</div>'
            f'<div style="font-size:.82rem;color:#8b93a7">skor {p["score"]:.2f}</div>'
            f'</div>'
        )
    plan_html += '</div></div>'
    st.markdown(plan_html, unsafe_allow_html=True)
    st.caption("Rencana ini akan berubah seiring data baru tersedia — periksa kembali setiap menjelang deadline.")
else:
    st.info("Belum cukup data untuk menyusun rencana chip.")

st.divider()

# --- Detail per Chip (4 columns) ---
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
            tc_df.style
            .map(lambda v: "color:#0f172a;font-weight:400;text-align:center", subset=["GW", "Laga Mudah", "Kapten (est)", "Proyeksi", "TC Skor"])
            .apply(highlight_max, subset=["TC Skor"])
            .format({"Proyeksi": "{:.2f}", "TC Skor": "{:.2f}"})
            .hide(axis="index"),
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
          <div class="info-line">1. Cadangan Anda kuat (proyeksi 4 terendah &ge; ±8 poin).</div>
          <div class="info-line">2. Banyak pemain tim Anda main 2 laga (DGW).</div>
          <div class="info-line">3. Semua pemain bebas cedera/suspensi.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if has_squad:
        bench = bench_players(squad)
        bb_now = bb_estimate(gw_summary(gd, ev["id"]), squad)
        st.markdown(
            f"<div class='info-line'>Nilai cadangan GW ini: <span style='color:#37003c;font-weight:600'>{bb_now['score']:.2f}</span> poin.</div>",
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
                bb_df.style
                .map(lambda v: "color:#0f172a;font-weight:400;text-align:center", subset=["GW", "Laga Mudah", "Pemain DGW", "BB Skor"])
                .apply(highlight_max, subset=["BB Skor"])
                .format({"BB Skor": "{:.2f}"})
                .hide(axis="index"),
                use_container_width=True,
                hide_index=True,
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

# --- Wildcard & Free Hit (NEW) ---
c1, c2 = st.columns(2)

with c1:
    st.markdown('<div class="section" style="font-size:1rem">Wildcard <em>(WC)</em></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="fpl-card">
          <h3>Kapan WC paling bernilai?</h3>
          <div class="card-sub">WC memungkinkan rebuild total tanpa penalti transfer. Gunakan saat:</div>
          <div class="info-line">1. Banyak pemain skuad underperform atau cedera.</div>
          <div class="info-line">2. Ada fixture swing besar — banyak tim beralih dari lawan sulit ke mudah.</div>
          <div class="info-line">3. Menjelang DGW — rebuild untuk memaksimalkan pemain DGW.</div>
          <div class="info-line">4. Paruh musim — WC kedua tersedia setelah GW 20.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    wc_rows = []
    for g in cal:
        w = wc_estimate(g, gd, df, squad if has_squad else None)
        if w:
            wc_rows.append({
                "GW": g["event"],
                "Laga Mudah (3GW)": w["future_easy_fixtures"],
                "Tim DGW": w["dgw_teams"],
                "Underperform": len(w["underperformers"]),
                "WC Skor": w["score"],
            })
    if wc_rows:
        wc_df = pd.DataFrame(wc_rows).sort_values("WC Skor", ascending=False).head(5)
        st.dataframe(
            wc_df.style
            .map(lambda v: "color:#0f172a;font-weight:400;text-align:center", subset=["GW", "Laga Mudah (3GW)", "Tim DGW", "Underperform", "WC Skor"])
            .apply(highlight_max, subset=["WC Skor"])
            .format({"WC Skor": "{:.2f}"})
            .hide(axis="index"),
            use_container_width=True,
            hide_index=True,
        )
        best_wc = wc_df.iloc[0]
        st.success(
            f"Rekomendasi: pertimbangkan WC di **GW {int(best_wc['GW'])}** — "
            f"{int(best_wc['Laga Mudah (3GW)'])} laga mudah dalam 3 GW, "
            f"{int(best_wc['Underperform'])} pemain underperform. Skor WC: {best_wc['WC Skor']:.2f}."
        )

with c2:
    st.markdown('<div class="section" style="font-size:1rem">Free Hit <em>(FH)</em></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="fpl-card">
          <h3>Kapan FH paling bernilai?</h3>
          <div class="card-sub">FH memungkinkan tim berbeda untuk 1 GW saja. Gunakan saat:</div>
          <div class="info-line">1. Blank Gameweek (BGW) — banyak tim tidak bermain.</div>
          <div class="info-line">2. Banyak pemain skuad Anda tidak bertanding di GW itu.</div>
          <div class="info-line">3. Tidak ada DGW — simpan TC/BB untuk DGW, pakai FH di BGW.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    fh_rows = []
    for g in cal:
        fh = fh_estimate(g, gd, df)
        if fh:
            fh_rows.append({
                "GW": g["event"],
                "Tim Blank": fh["n_blank_teams"],
                "BGW?": "Ya" if fh["is_bgw"] else "Tidak",
                "FH Skor": fh["score"],
            })
    if fh_rows:
        fh_df = pd.DataFrame(fh_rows).sort_values("FH Skor", ascending=False).head(5)
        st.dataframe(
            fh_df.style
            .map(lambda v: "color:#0f172a;font-weight:400;text-align:center", subset=["GW", "Tim Blank", "BGW?", "FH Skor"])
            .apply(highlight_max, subset=["FH Skor"])
            .format({"FH Skor": "{:.2f}"})
            .hide(axis="index"),
            use_container_width=True,
            hide_index=True,
        )
        best_fh = fh_df.iloc[0]
        if best_fh["Tim Blank"] > 0:
            st.success(
                f"Rekomendasi: gunakan FH di **GW {int(best_fh['GW'])}** — "
                f"{int(best_fh['Tim Blank'])} tim tidak bermain (Blank GW). Skor FH: {best_fh['FH Skor']:.2f}."
            )
        else:
            st.info(
                "Belum ada Blank GW terdeteksi — simpan Free Hit sampai BGW muncul. "
                "FPL biasanya mengumumkan BGW mendekati paruh musim kedua."
            )

st.divider()
st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem'>"
    "Estimasi GW mendatang memakai proyeksi pemain saat ini sebagai patokan (data per pemain per GW "
    "baru tersedia saat GW berjalan). Pantau ulang setiap menjelang deadline.</p>",
    unsafe_allow_html=True,
)
