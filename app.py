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
    player_img_html,
    pos_badge_html,
    refresh,
)
from fpl.utils import fmt_deadline_wib, fmt_price

st.set_page_config(page_title="FPL Dashboard - Beranda", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event

# --- Auto-save projections for accuracy tracking ---
try:
    from fpl.accuracy import auto_update_history, save_projections
    save_projections(ev.get("id"), df)
    # Auto-fetch actuals for all past GWs
    auto_update_history()
except Exception:
    pass

st.markdown(
    f"""
    <div class="fpl-hero">
      <div class="kicker">Fantasy Premier League · Toolkit</div>
      <h1>FPL Dashboard</h1>
      <div class="sub">Rekomendasi kapten, transfer, dan line-up berbasis data untuk Gameweek {ev.get('id')}.</div>
      <div class="updated">Data terakhir diperbarui: {last_updated()} | ⏰ Deadline GW {ev.get('id')}: <b>{fmt_deadline_wib(ev.get('deadline_time'), format_type='full')}</b></div>
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

# --- Stats bar ---
top_cap = df.dropna(subset=["proj"]).sort_values("proj", ascending=False).iloc[0]
st.markdown(
    f"""
    <div class="stat-bar">
      <div class="stat-item"><div class="sv">GW {ev.get('id')}</div><div class="sl">Gameweek</div></div>
      <div class="stat-item"><div class="sv">{len(df)}</div><div class="sl">Total Pemain</div></div>
      <div class="stat-item"><div class="sv">{len(gd.fixtures_by_team) // 2}</div><div class="sl">Pertandingan</div></div>
      <div class="stat-item"><div class="sv">{top_cap['web_name']}</div><div class="sl">Kapten Rekomendasi</div></div>
      <div class="stat-item"><div class="sv" style="color:#37003c">{top_cap['proj']:.2f}pts</div><div class="sl">Proyeksi Tertinggi</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="section">Rekomendasi <em>Kapten</em></div>', unsafe_allow_html=True)
top3 = df.dropna(subset=["proj"]).sort_values("proj", ascending=False).head(3)
cards = st.columns(3)
tags = ["KAPTEN", "WAKIL", "ALT"]
for col, (_, row), tag in zip(cards, top3.iterrows(), tags):
    with col:
        st.markdown(player_card_html(row, tag=tag), unsafe_allow_html=True)

# --- Monte-Carlo captain EV (quick) ---
try:
    from fpl.simulator import captain_analysis, load_saved_squad, reference_xi

    mc_squad, mc_xi, mc_src = load_saved_squad(df)
    if mc_squad is None:
        mc_squad = reference_xi(df)
        mc_xi = None
    mc = captain_analysis(gd, df, mc_squad, xi_ids=mc_xi, n=300, seed=7)
    t = mc["top"]
    mc_c1, mc_c2, mc_c3 = st.columns(3)
    with mc_c1:
        st.metric("🎲 EV Kapten (Monte Carlo)", f"{t['web_name']} — {t['ev_captain']:.1f} pts",
                  help=f"Wakil terbaik: {t['best_vc_name'] or '-'} (EV {t['ev_best_vc_effect']:.2f}). Proyeksi titik: {t['proj']:.2f}")
    with mc_c2:
        st.metric("Peluang kapten dimainkan", f"{t['p_plays'] * 100:.0f}%",
                  help="Dari simulasi menit main per pemain (chance_of_playing + rata-rata menit).")
    with mc_c3:
        st.metric("Rentang p10–p90 poin kapten", f"{mc['cap_distribution']['p10']:.0f} – {mc['cap_distribution']['p90']:.0f}",
                  help="Distribusi 300 skenario. EV ≠ kepastian: kapten dengan EV mirip tapi rentang lebih sempit = pilihan lebih aman.")
    st.caption(f"Sumber skuad simulasi: {mc_src if mc_src else 'XI referensi (simpan skuad via Team Builder untuk hasil sesuai tim Anda)'} · lihat detail lengkap di halaman **Kapten & Transfer**.")
except Exception:
    pass

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
rows = "<div class='fpl-card'><div style='display:flex;flex-direction:column;gap:10px'>"
for rank, (_, p) in enumerate(top.iterrows(), 1):
    home = "Kandang" if p.get("is_home") else "Tandang"
    dgw_tag = " <span class='fdr-badge fdr-2'>DGW</span>" if p.get("n_fixtures", 1) >= 2 else ""
    rows += (
        f'<div style="display:flex;align-items:center;gap:12px;font-size:.82rem">'
        f'<span style="width:20px;font-weight:500;color:#94a3b8">{rank}</span>'
        f'{player_img_html(p, style="width:34px;height:42px;object-fit:contain;background:#f8fafc;border-radius:6px")}'
        f'<span style="font-weight:500;color:#0f172a;min-width:150px">{esc(p["web_name"])}</span>'
        f'<span style="min-width:56px">{pos_badge_html(p["pos"])}</span>'
        f'<span style="color:#64748b;min-width:65px">{esc(p["team_short"])}</span>'
        f'<span style="color:#64748b;min-width:60px">{fmt_price(p["price"])}</span>'
        f'<span style="color:#475569;flex:1">vs {esc(p["opponent_short"])} · {home}{dgw_tag}</span>'
        f'{fdr_badge_html(p.get("fdr"))}'
        f'<span style="font-weight:600;color:#37003c;min-width:50px;text-align:right">{p["proj"]:.2f}</span>'
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
    "Tanda <span style='color:#37003c;font-weight:600'>DOUBLE</span> = poin tinggi musim lalu DAN proyeksi tinggi sekarang."
)

from fpl.paststats import attach, indicator as past_indicator, load as load_past

with st.spinner("Memuat statistik musim lalu..."):
    dfp = attach(df, load_past(gd))
stars = dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0)].nlargest(10, "last_points")
rows = "<div class='fpl-card'><div style='display:flex;flex-direction:column;gap:10px'>"
for rank, (_, p) in enumerate(stars.iterrows(), 1):
    double = "<span class='fdr-badge fdr-2'>DOUBLE</span>" if p["proj"] and p["proj"] >= 2.2 else ""
    proj_txt = f"{p['proj']:.2f}" if p["proj"] is not None else "-"
    rows += (
        f'<div style="display:flex;align-items:center;gap:12px;font-size:.82rem">'
        f'<span style="width:20px;font-weight:500;color:#94a3b8">{rank}</span>'
        f'<span style="font-weight:500;color:#0f172a;min-width:150px">{esc(p["web_name"])}</span>'
        f'<span style="min-width:54px">{pos_badge_html(p["pos"])}</span>'
        f'<span style="color:#64748b;min-width:50px">{esc(p["team_short"])}</span>'
        f'<span style="font-weight:500;color:#d97706;min-width:70px">{int(p["last_points"])} pts</span>'
        f'<span style="color:#64748b;min-width:60px">ppg {p["last_ppg"]:.2f}</span>'
        f'<span style="color:#64748b;min-width:60px">{fmt_price(p["price"])}</span>'
        f'<span style="color:#475569;flex:1">proyeksi GW ini: <span style="color:#0f172a;font-weight:500">{proj_txt}</span></span>'
        f'{double}</div>'
    )
rows += "</div></div>"
st.markdown(rows, unsafe_allow_html=True)

# --- Rotation Risk Alert ---
st.markdown('<div class="section">⚠️ Peringatan <em>Risiko Rotasi</em></div>', unsafe_allow_html=True)
try:
    from fpl.optimizer import rotation_risk

    all_players = df.to_dict("records")
    risks = rotation_risk(all_players)
    if risks:
        risk_rows = '<div class="fpl-card"><div style="display:flex;flex-direction:column;gap:8px">'
        for r in risks[:8]:
            p = r["player"]
            sev_color = "#dc2626" if r["severity"] == "high" else "#f59e0b"
            sev_icon = "🔴" if r["severity"] == "high" else "🟡"
            reasons_txt = " · ".join(r["reasons"])
            risk_rows += (
                f'<div style="display:flex;align-items:center;gap:10px;font-size:.82rem;padding:6px 0;border-bottom:1px solid #f1f5f9">'
                f'<span>{sev_icon}</span>'
                f'<span style="font-weight:500;color:#0f172a;min-width:130px">{esc(p["web_name"])}</span>'
                f'<span style="min-width:54px">{pos_badge_html(p["pos"])}</span>'
                f'<span style="color:#64748b;min-width:50px">{esc(p["team_short"])}</span>'
                f'<span style="color:{sev_color};flex:1">{reasons_txt}</span>'
                f'</div>'
            )
        risk_rows += '</div></div>'
        st.markdown(risk_rows, unsafe_allow_html=True)
        st.caption("Pemain di atas memiliki risiko tidak bermain penuh. Pastikan bench order Anda optimal!")
    else:
        st.success("Tidak ada pemain dengan risiko rotasi tinggi saat ini.")
except Exception:
    pass

# --- Bench Order Recommendation ---
st.markdown('<div class="section">🪑 Rekomendasi <em>Urutan Bench</em></div>', unsafe_allow_html=True)
st.caption(
    "Urutan bench menentukan siapa yang masuk saat ada starter yang tidak bermain (auto-sub). "
    "GK bench selalu di posisi 4; outfield diurutkan berdasarkan proyeksi tertinggi."
)
try:
    from fpl.optimizer import ordered_bench

    top_players = df.dropna(subset=["proj"]).sort_values("proj", ascending=False).head(15).to_dict("records")
    # Show an example optimal bench for top-15 projected
    bench_example = [p for p in top_players if p["proj"] is not None]
    if len(bench_example) >= 4:
        bench_4 = bench_example[-4:]  # Lowest projected from top-15
        optimal = ordered_bench(bench_4)
        bench_html = '<div class="fpl-card"><div class="bench-row">'
        for i, p in enumerate(optimal, 1):
            pos_label = "(GK cadangan)" if p["pos"] == "GK" else f"Sub ke-{i}"
            bench_html += (
                f'<div class="bench-cell">'
                f'<span class="n">{esc(p["web_name"])}</span>'
                f'<span class="x">{pos_label} · proyeksi {p["proj"]:.2f}</span>'
                f'</div>'
            )
        bench_html += '</div></div>'
        st.markdown(bench_html, unsafe_allow_html=True)
except Exception:
    pass

# --- Accuracy Summary ---
st.markdown('<div class="section" style="font-size:.95rem">Akurasi <em>Model</em> Proyeksi</div>', unsafe_allow_html=True)
try:
    from fpl.accuracy import history as acc_history

    hist = acc_history()
    completed = [h for h in hist if h["metrics"] is not None]
    if completed:
        latest = completed[-1]
        m = latest["metrics"]
        c1, c2, c3 = st.columns(3)
        c1.metric("MAE (GW terakhir)", f"{m['mae']:.2f}", f"GW {latest['gw']}")
        c2.metric("RMSE (GW terakhir)", f"{m['rmse']:.2f}", f"{m['n']} pemain dievaluasi")
        avg_mae = sum(h["metrics"]["mae"] for h in completed) / len(completed)
        c3.metric("MAE rata-rata musim", f"{avg_mae:.2f}", f"{len(completed)} GW data")
        st.caption("Lihat detail lengkap di halaman **Akurasi Model** (sidebar).")
    else:
        st.info(
            "Belum ada data akurasi — proyeksi otomatis disimpan setiap GW. "
            "Setelah GW pertama selesai, buka halaman **Akurasi Model** untuk melihat evaluasi."
        )
except Exception:
    st.caption("Modul akurasi belum tersedia.")

st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem;margin-top:24px'>"
    "Semua angka adalah estimasi berbasis statistik (form, xGI, FDR, kandang/tandang, CS probability, proyeksi FPL). "
    "Keputusan akhir tetap di tangan Anda.</p>",
    unsafe_allow_html=True,
)
