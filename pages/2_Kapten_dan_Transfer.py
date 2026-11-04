"""Kapten & Transfer — simple tabs for captain, transfer, and market."""

import pandas as pd
import streamlit as st

from fpl.availability import availability
from fpl.optimizer import overpriced_players, projection_explanation, risk_players, value_picks
from fpl.ui import (
    FDR_CELL,
    apply_theme,
    autorefresh,
    esc,
    load_data,
    player_card_html,
    pos_badge_html,
    transfer_card_html,
)
from fpl.ui_simple import (
    confidence_badge,
    is_beginner,
    simple_hero,
    simple_note,
    status_pill,
)
from fpl.utils import fmt_price

st.set_page_config(page_title="Kapten & Transfer", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event
gw_id = int(ev["id"])

from fpl.paststats import attach, load as load_past

with st.spinner("Memuat statistik musim lalu..."):
    dfp = attach(df, load_past(gd))

simple_hero(
    "Kapten & Transfer",
    "Bandingkan kandidat dan cari pemain. Keputusan utama tetap ada di halaman Minggu Ini.",
    kicker="Perbandingan · Bukan Wajib Dibaca Semua",
)
st.caption("← Kembali ke Minggu Ini lewat sidebar")

players = df.to_dict("records")
available = [p for p in players if p.get("proj") and p["proj"] > 0]

# Shared squad state for the transfer tab.
from fpl.horizon import player_gw_projections
from fpl.planner import manager_state
from fpl.simulator import captain_analysis, load_saved_squad, reference_xi
from fpl.transfer import differential_picks, fixture_ticker_table, hit_calculator, injury_transfer_suggestions

squad_rows, xi_ids, src_label = load_saved_squad(df)
state = manager_state(df, current_gw=gw_id)
if state:
    squad_rows = state["squad_rows"]
    bank_tenths = int(state["bank"])
    sell_prices = state["sell_prices"]
    source = f"Tim FPL {state.get('team_name') or state.get('team_id')} · FT {state.get('free_transfers')}"
else:
    bank_tenths = 0
    sell_prices = {}
    if squad_rows is None:
        squad_rows = reference_xi(df)
        source = "XI referensi (belum ada skuad tersimpan)"
    else:
        source = src_label

tabs = st.tabs(["🎯 Kapten", "🔄 Transfer", "🔎 Pasar"])

# ===========================================================================
# TAB 1 — CAPTAIN
# ===========================================================================
with tabs[0]:
    st.markdown("### Kandidat kapten")
    st.caption("Kapten mendapat 2× poin. Pilih yang keseimbangan poin, peluang main, dan risikonya paling cocok.")

    top5 = sorted(available, key=lambda p: p["proj"], reverse=True)[:5]
    tags = ["KAPTEN", "WAKIL", "ALT", "ALT", "ALT"]
    cols = st.columns(5)
    for col, p, tag in zip(cols, top5, tags):
        with col:
            st.markdown(player_card_html(p, tag=tag), unsafe_allow_html=True)

    risk_profile = st.radio(
        "Profil risiko",
        options=["Seimbang (EV)", "Aman (EV − varians)", "Agresif (EV + ceiling)"],
        horizontal=True,
        key="captain_risk_profile",
        help="Aman mengurangi kapten dengan varians tinggi; Agresif memberi bobot lebih pada peluang haul ≥10 poin.",
    )
    with st.spinner("Menjalankan simulasi kapten..."):
        mc = captain_analysis(gd, df, squad_rows, xi_ids=xi_ids if len(squad_rows) == 15 else None, n=900, seed=7)

    def _score(c):
        ev = float(c.get("ev_captain") or 0)
        se = float(c.get("ev_se") or 0)
        haul = float(c.get("p_haul") or 0)
        if risk_profile.startswith("Aman"):
            return ev - se
        if risk_profile.startswith("Agresif"):
            return ev + 2.0 * haul
        return ev

    ranked = sorted(mc["candidates"], key=_score, reverse=True)
    top = ranked[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kapten rekomendasi", top["web_name"], f"proyeksi {top['proj']:.1f}")
    c2.metric("Perkiraan poin kapten", f"{top['ev_captain']:.1f}")
    c3.metric("Peluang main", f"{top['p_plays'] * 100:.0f}%")
    c4.metric("Risiko blank", f"{top['p_blank'] * 100:.0f}%")
    st.markdown(
        f"{confidence_badge('Tinggi' if top['p_plays'] >= 0.95 else 'Sedang' if top['p_plays'] >= 0.75 else 'Rendah')} "
        f"&nbsp; Wakil terbaik: **{top.get('best_vc_name') or '-'}**. "
        "Kalau kapten tidak main, wakil otomatis menggantikan."
    )

    rows = []
    for c in ranked[:8]:
        row = {
            "Pemain": c["web_name"],
            "Tim": c["team_short"],
            "Perkiraan poin": round(c["ev_captain"], 1),
            "Main": f"{c['p_plays'] * 100:.0f}%",
            "Blank": f"{c['p_blank'] * 100:.0f}%",
            "Haul ≥10": f"{c.get('p_haul', 0) * 100:.0f}%",
            "Kepemilikan": f"{c.get('selected_by', 0):.1f}%",
        }
        if not is_beginner():
            row["EV ± SE"] = f"{c['ev_captain']:.1f} ± {c.get('ev_se', 0):.2f}"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("💡 Kenapa kapten ini?"):
        st.write(
            f"**{top['web_name']}** punya kombinasi perkiraan poin, peluang main, dan potensi haul yang terbaik "
            f"untuk profil **{risk_profile}**."
        )
        st.write(
            f"Alternatif aman: **{ranked[1]['web_name'] if len(ranked) > 1 else '-'}** · "
            f"Alternatif agresif: **{max(ranked, key=lambda c: c.get('p_haul', 0))['web_name']}**."
        )
        if not is_beginner():
            for c in ranked[:3]:
                st.write(
                    f"- {c['web_name']}: EV {c['ev_captain']:.2f} ± {c.get('ev_se', 0):.2f}, "
                    f"p10–p90 {c.get('p10', '-')}–{c.get('p90', '-')}, haul {c.get('p_haul', 0) * 100:.0f}%."
                )

    with st.expander("Detail perhitungan proyeksi"):
        for p in top5[:3]:
            st.write(f"**{p['web_name']}**")
            st.code(projection_explanation(p))

# ===========================================================================
# TAB 2 — TRANSFER
# ===========================================================================
with tabs[1]:
    st.markdown("### Transfer karena cedera / peluang main")
    st.caption(f"Sumber skuad: {source}. Pemain masuk dengan peluang 0% tidak disarankan.")
    min_chance = st.slider(
        "Peluang main minimum untuk pemain masuk",
        min_value=0, max_value=100, value=0, step=25,
        help="0% = hanya menolak pemain yang tidak tersedia. 75% = hindari pemain diragukan.",
    )

    with st.spinner("Menghitung rekomendasi transfer..."):
        gw_projs = player_gw_projections(df, gd, horizon=3)
        suggestions = injury_transfer_suggestions(
            squad_rows, players, gw_projs, bank=bank_tenths, horizon=3,
            sell_prices=sell_prices, min_in_chance=min_chance,
        )

    if not suggestions:
        st.success("Tidak ada pemain skuad dengan status cedera/diragukan. Tidak ada transfer darurat.")
    else:
        for s in suggestions:
            out = s["player"]
            av = s["availability"]
            rep = s["replacement"]
            extra = (
                f"<span class='fdr-badge' style='background:{'#dc2626' if av['pct'] <= 0 else '#d97706'};color:#fff'>"
                f"{esc(s['action'])}</span>"
            )
            if rep:
                hit = hit_calculator(out, rep, gw_projs, horizon=3)
                net = hit["net_after_hit"]
                extra += (
                    f"<span class='fdr-badge' style='background:{'#16a34a' if net > 0 else '#dc2626'};color:#fff'>"
                    f"Net jika hit −4: {net:+.1f}</span>"
                )
            st.html(transfer_card_html(
                out, rep, s["player_total"], s["replacement_total"] or 0, s["gain"],
                extra_badges=extra,
            ))

    with st.expander("Lihat semua pemain cedera / diragukan / suspended"):
        risk_rows = []
        for p in players:
            av = availability(p)
            if av["status"] == "a" and av["pct"] >= 100:
                continue
            kabar = av["news"] or "-"
            if av["return_text"]:
                kabar = f"{kabar} · kembali: {av['return_text']}"
            risk_rows.append({
                "Pemain": p["web_name"], "Tim": p["team_short"],
                "Status": av["status_label"], "Peluang GW ini": f"{av['this_pct']:.0f}%",
                "Peluang GW depan": f"{av['next_pct']:.0f}%", "Kabar": kabar[:110],
                "_own": p["selected_by"],
            })
        if risk_rows:
            risk_df = pd.DataFrame(risk_rows).sort_values("_own", ascending=False).drop(columns=["_own"]).head(40)
            st.dataframe(risk_df, use_container_width=True, hide_index=True)
        else:
            st.success("Tidak ada pemain berstatus cedera/diragukan/suspended.")

    with st.expander("Cara menghitung hit −4"):
        st.write(
            "Transfer ekstra di luar FT dikenai −4 poin. Bandingkan gain proyeksi 3 GW dengan penalti tersebut. "
            "Kalau net gain negatif atau sangat kecil, simpan FT."
        )

# ===========================================================================
# TAB 3 — MARKET
# ===========================================================================
with tabs[2]:
    st.markdown("### Jadwal lawan 6 GW")
    st.caption("Semakin hijau, semakin mudah. ⚡ = Double Gameweek.")
    ticker_rows, cur_gw = fixture_ticker_table(gd, n_gws=6)
    ticker_html = '<div class="fpl-card" style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:.8rem">'
    ticker_html += '<tr style="border-bottom:1px solid #e2e8f0;background:#f8fafc">'
    ticker_html += '<th style="text-align:left;padding:8px 10px;color:#475569;font-weight:500">Tim</th>'
    for i in range(6):
        ticker_html += f'<th style="text-align:center;padding:8px 6px;color:#475569;font-weight:500">GW {cur_gw + i}</th>'
    ticker_html += '<th style="text-align:center;padding:8px 6px;color:#475569;font-weight:500">Avg</th></tr>'
    for row in ticker_rows:
        ticker_html += '<tr style="border-bottom:1px solid #f1f5f9">'
        ticker_html += f'<td style="padding:6px 10px;font-weight:500;color:#0f172a">{esc(row["team_short"])}</td>'
        for i in range(6):
            gw = cur_gw + i
            cell = row.get(f"gw_{gw}", {"text": "-", "fdr": None})
            bg, text_color = FDR_CELL.get(cell.get("fdr"), ("#f8fafc", "#475569"))
            dgw_mark = " ⚡" if cell.get("dgw") else ""
            ticker_html += f'<td style="text-align:center;padding:5px 4px;background:{bg};color:{text_color};font-weight:500;font-size:.7rem">{esc(cell["text"])}{dgw_mark}</td>'
        avg = row.get("avg_fdr", 3.0)
        avg_color = "#15803d" if avg <= 2.5 else "#d97706" if avg <= 3.5 else "#b91c1c"
        ticker_html += f'<td style="text-align:center;padding:5px;color:{avg_color};font-weight:600">{avg:.1f}</td></tr>'
    ticker_html += '</table></div>'
    st.markdown(ticker_html, unsafe_allow_html=True)

    st.markdown("### Value picks")
    st.caption("Poin proyeksi per £1 juta. Cocok untuk mencari pemain murah.")
    vps = value_picks(available, n=40)
    for pos in ("GK", "DEF", "MID", "FWD"):
        subset = [p for p in vps if p["pos"] == pos][:5]
        if not subset:
            continue
        with st.expander(f"{pos} — 5 terbaik", expanded=(pos == "MID")):
            for p in subset:
                st.markdown(
                    f"<div class='info-line'><b>{esc(p['web_name'])}</b> "
                    f"({esc(p['team_short'])}) · {fmt_price(p['price'])} · "
                    f"proyeksi {p['proj']:.2f} · value {p['value']:.2f} pts/£1jt</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("### Differential picks")
    st.caption("Kepemilikan <5% tetapi proyeksi tinggi. Untuk mengejar rank.")
    diffs = differential_picks(available, ownership_threshold=5.0, min_proj=2.0, n=10)
    if diffs:
        cols = st.columns(5)
        for col, p in zip(cols, diffs[:5]):
            with col:
                st.markdown(
                    f'<div class="p-card"><div class="tag alt">DIFF {p["selected_by"]:.1f}%</div>'
                    f'<div class="p-name">{esc(p["web_name"])}</div>'
                    f'<div class="p-team">{esc(p["team_short"])} {pos_badge_html(p["pos"])}</div>'
                    f'<div class="p-proj">{p["proj"]:.2f}</div>'
                    f'<div class="p-sub">{fmt_price(p["price"])}</div></div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("Tidak ada differential pick yang memenuhi kriteria.")

    st.markdown("### Pemain berisiko & harga mahal")
    c1, c2 = st.columns(2)
    with c1:
        risky = risk_players(players)
        if risky:
            for p in risky[:8]:
                av = availability(p)
                st.markdown(
                    f"<div class='info-line'><b style='color:#dc2626'>{esc(p['web_name'])}</b> "
                    f"({esc(p['team_short'])}) · {p['selected_by']:.1f}% · {esc(av['label'])}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("Tidak ada pemain berisiko.")
    with c2:
        over = overpriced_players(players)
        if over:
            for p in over[:8]:
                st.markdown(
                    f"<div class='info-line'><b style='color:#d97706'>{esc(p['web_name'])}</b> "
                    f"({esc(p['team_short'])}) · {fmt_price(p['price'])} · proyeksi {p['proj']:.2f}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("Tidak ada pemain mahal dengan proyeksi rendah.")

    with st.expander("Acuan musim lalu (2025/26)"):
        stars = dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0)].nlargest(10, "last_points")
        for p in stars.to_dict("records"):
            st.markdown(
                f"<div class='info-line'><b style='color:#f59e0b'>{int(p['last_points'])} pts</b> — "
                f"<b>{esc(p['web_name'])}</b> ({esc(p['team_short'])}, {p['pos']}, {fmt_price(p['price'])}) · "
                f"ppg lalu {p['last_ppg']:.2f} · proyeksi GW ini <b style='color:#37003c'>{p['proj']:.2f}</b></div>",
                unsafe_allow_html=True,
            )

simple_note(
    "Halaman ini untuk membandingkan. Kalau bingung, kembali ke <b>Minggu Ini</b> — "
    "di sana hanya ada keputusan utama."
)
