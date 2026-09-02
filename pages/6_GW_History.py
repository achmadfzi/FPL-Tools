import plotly.graph_objects as go
import streamlit as st

from fpl.gw_history import chip_impact, fetch_season_history, optimal_captain_calc
from fpl.team import get_saved_team_id
from fpl.ui import apply_theme, autorefresh, esc, load_data
from fpl.utils import fmt_price

st.set_page_config(page_title="GW History", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event

st.markdown('<div class="section">Gameweek <em>History</em> & Points Timeline</div>', unsafe_allow_html=True)
st.caption("Visualisasi perjalanan timmu sepanjang musim — rank, poin, chip impact, dan analisis kapten.")

# --- Get Team ID ---
saved_id = get_saved_team_id()

c1, c2 = st.columns([2, 3])
with c1:
    team_id = st.text_input(
        "FPL Team ID",
        value=str(saved_id) if saved_id else "",
        placeholder="contoh: 925693",
    )
with c2:
    st.caption("Masukkan FPL Team ID kamu. Bisa dilihat di URL profil FPL kamu.")

if not team_id:
    st.info("Masukkan FPL Team ID untuk melihat histori musim ini.")
    st.stop()

try:
    team_id = int(str(team_id).strip())
except (ValueError, TypeError):
    st.error("Team ID harus berupa angka.")
    st.stop()

# --- Fetch History ---
with st.spinner("Memuat histori musim..."):
    history = fetch_season_history(team_id)

if history.get("error"):
    st.error(f"Gagal memuat data: {history['error']}")
    st.stop()

gw_results = history.get("gw_results", [])
if not gw_results:
    st.warning("Belum ada data GW yang selesai untuk tim ini.")
    st.stop()

# --- Manager Profile ---
st.markdown(
    f"""
    <div class="fpl-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
        <div>
          <h3 style="margin:0">{esc(history.get('team_name', 'FPL Team'))}</h3>
          <div style="color:#64748b;font-size:.85rem">Manager: {esc(history.get('manager_name', '-'))}</div>
        </div>
        <div style="display:flex;gap:24px;text-align:center">
          <div>
            <div style="font-size:1.4rem;font-weight:700;color:#37003c">{history.get('overall_points', 0)}</div>
            <div style="font-size:.72rem;color:#94a3b8">Total Poin</div>
          </div>
          <div>
            <div style="font-size:1.4rem;font-weight:700;color:#37003c">{history.get('overall_rank', 0):,}</div>
            <div style="font-size:.72rem;color:#94a3b8">Overall Rank</div>
          </div>
          <div>
            <div style="font-size:1.4rem;font-weight:700;color:#0ea5e9">{history.get('avg_points_per_gw', 0)}</div>
            <div style="font-size:.72rem;color:#94a3b8">Rata-rata/GW</div>
          </div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Key Stats ---
best = history.get("best_gw")
worst = history.get("worst_gw")

c1, c2, c3, c4 = st.columns(4)
if best:
    c1.metric("🏆 GW Terbaik", f"{best['points']} pts", f"GW {best['gw']}")
if worst:
    c2.metric("📉 GW Terburuk", f"{worst['points']} pts", f"GW {worst['gw']}")
c3.metric("💸 Total Hit", f"-{history.get('total_hits', 0)} pts",
          f"{sum(1 for g in gw_results if g['transfers_cost'] > 0)} transfer hit")
c4.metric("🪑 Poin di Bench", f"{history.get('total_bench_pts', 0)} pts",
          f"rata-rata {round(history.get('total_bench_pts', 0) / max(len(gw_results), 1), 1)}/GW")

# --- Overall Rank Progression Chart ---
st.markdown('<div class="section" style="font-size:.95rem">📈 Perjalanan <em>Overall Rank</em></div>', unsafe_allow_html=True)

ranks = [g["overall_rank"] for g in gw_results if g["overall_rank"] > 0]
gws = [g["gw"] for g in gw_results if g["overall_rank"] > 0]

if ranks:
    fig_rank = go.Figure()
    fig_rank.add_trace(go.Scatter(
        x=gws, y=ranks,
        mode="lines+markers",
        name="Overall Rank",
        line=dict(color="#37003c", width=3),
        marker=dict(size=10, color="#37003c"),
        fill="tozeroy",
        fillcolor="rgba(55,0,60,0.08)",
    ))
    fig_rank.update_layout(
        yaxis=dict(autorange="reversed", title="Rank (lebih rendah = lebih baik)"),
        xaxis_title="Gameweek",
        height=350,
        paper_bgcolor="#fff", plot_bgcolor="#f8f9fb",
        font=dict(color="#1a1a2e", size=11),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_rank, use_container_width=True)
    st.caption("Rank dibalik — semakin rendah (atas chart) semakin baik. Pergeseran tajam ke bawah = GW buruk.")

# --- Points per GW vs Average ---
st.markdown('<div class="section" style="font-size:.95rem">📊 Poin per GW <em>vs Rata-rata</em></div>', unsafe_allow_html=True)

gw_nums = [g["gw"] for g in gw_results]
gw_points = [g["points"] for g in gw_results]
gw_avg = [g["average"] for g in gw_results]

fig_pts = go.Figure()
fig_pts.add_trace(go.Bar(
    x=gw_nums, y=gw_points, name="Poin Kamu",
    marker_color=["#15803d" if p >= a else "#dc2626" for p, a in zip(gw_points, gw_avg)],
    text=gw_points, textposition="outside",
))
fig_pts.add_trace(go.Scatter(
    x=gw_nums, y=gw_avg, name="Rata-rata Global",
    mode="lines+markers",
    line=dict(color="#94a3b8", width=2, dash="dot"),
    marker=dict(size=6, color="#94a3b8"),
))
fig_pts.update_layout(
    xaxis_title="Gameweek", yaxis_title="Poin",
    height=350,
    paper_bgcolor="#fff", plot_bgcolor="#f8f9fb",
    font=dict(color="#1a1a2e", size=11),
    margin=dict(l=10, r=10, t=10, b=10),
    legend=dict(orientation="h", y=1.1),
    barmode="overlay",
)
st.plotly_chart(fig_pts, use_container_width=True)
st.caption("Hijau = di atas rata-rata, Merah = di bawah rata-rata. Garis putus-putus = rata-rata global FPL.")

beats = sum(1 for p, a in zip(gw_points, gw_avg) if p >= a)
st.success(f"Kamu mengalahkan rata-rata di **{beats}/{len(gw_results)}** Gameweek ({round(beats/max(len(gw_results),1)*100)}%).")

# --- Team Value Progression ---
st.markdown('<div class="section" style="font-size:.95rem">💰 Perkembangan <em>Nilai Tim</em></div>', unsafe_allow_html=True)

values = [g["team_value"] for g in gw_results]
banks = [g["bank"] for g in gw_results]

fig_val = go.Figure()
fig_val.add_trace(go.Scatter(
    x=gw_nums, y=values, mode="lines+markers", name="Nilai Tim",
    line=dict(color="#0ea5e9", width=3), marker=dict(size=8),
))
fig_val.add_trace(go.Bar(
    x=gw_nums, y=banks, name="Sisa Bank",
    marker_color="rgba(14,165,233,0.2)",
))
fig_val.update_layout(
    xaxis_title="Gameweek", yaxis_title="£ Juta",
    height=280,
    paper_bgcolor="#fff", plot_bgcolor="#f8f9fb",
    font=dict(color="#1a1a2e", size=11),
    margin=dict(l=10, r=10, t=10, b=10),
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig_val, use_container_width=True)

# --- Chip Impact ---
st.markdown('<div class="section" style="font-size:.95rem">🃏 Dampak <em>Chip</em></div>', unsafe_allow_html=True)

chips = chip_impact(history)
if chips:
    chip_html = '<div class="fpl-card"><div style="display:flex;flex-direction:column;gap:12px">'
    for c in chips:
        gain_color = "#15803d" if c["gain"] > 0 else "#dc2626"
        gain_icon = "📈" if c["gain"] > 0 else "📉"
        bench_info = f" · Poin bench: {c['bench_pts']}" if c["chip_key"] == "bboost" else ""
        chip_html += (
            f'<div style="display:flex;align-items:center;gap:12px;font-size:.85rem;padding:8px 0;border-bottom:1px solid #f1f5f9">'
            f'<span style="font-weight:600;color:#37003c;min-width:120px">{esc(c["chip"])}</span>'
            f'<span style="color:#64748b">GW {c["gw"]}</span>'
            f'<span style="font-weight:600;min-width:60px">{c["points"]} pts</span>'
            f'<span style="color:{gain_color};font-weight:500">{gain_icon} {c["gain"]:+.1f} vs rata-rata{bench_info}</span>'
            f'</div>'
        )
    chip_html += '</div></div>'
    st.markdown(chip_html, unsafe_allow_html=True)
    st.caption("Gain dihitung vs rata-rata poin per GW kamu. Positif = chip berhasil meningkatkan performa.")
else:
    st.info("Belum ada chip yang digunakan musim ini, atau data chip belum tersedia.")

# --- Transfer Activity ---
st.markdown('<div class="section" style="font-size:.95rem">🔄 Aktivitas <em>Transfer</em></div>', unsafe_allow_html=True)

transfers_made = [g["transfers_made"] for g in gw_results]
transfers_cost = [g["transfers_cost"] for g in gw_results]

fig_tf = go.Figure()
fig_tf.add_trace(go.Bar(
    x=gw_nums, y=transfers_made, name="Transfer",
    marker_color=["#f59e0b" if c > 0 else "#0ea5e9" for c in transfers_cost],
    text=[f"-{c}" if c > 0 else "" for c in transfers_cost],
    textposition="outside", textfont=dict(color="#dc2626", size=10),
))
fig_tf.update_layout(
    xaxis_title="Gameweek", yaxis_title="Jumlah Transfer",
    height=250,
    paper_bgcolor="#fff", plot_bgcolor="#f8f9fb",
    font=dict(color="#1a1a2e", size=11),
    margin=dict(l=10, r=10, t=10, b=10),
)
st.plotly_chart(fig_tf, use_container_width=True)
st.caption("Kuning = transfer dengan hit (-4), Biru = transfer gratis.")

# --- Optimal Captain Analysis ---
st.markdown('<div class="section" style="font-size:.95rem">👑 Analisis <em>Kapten Optimal</em></div>', unsafe_allow_html=True)
st.caption(
    "Jika kamu selalu memilih pemain dengan skor tertinggi di skuadmu sebagai kapten, "
    "berapa total poin yang hilang/didapat?"
)

with st.spinner("Menghitung kapten optimal..."):
    cap_analysis = optimal_captain_calc(team_id)

if cap_analysis.get("error"):
    st.warning(cap_analysis["error"])
elif cap_analysis.get("details"):
    details = cap_analysis["details"]

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Poin Kapten Aktual",
        f"+{cap_analysis['total_actual_captain_pts']}",
        "bonus kapten total",
    )
    c2.metric(
        "Poin Kapten Optimal",
        f"+{cap_analysis['total_optimal_captain_pts']}",
        f"missed {cap_analysis['missed_total']:+} pts",
        delta_color="inverse" if cap_analysis["missed_total"] > 0 else "normal",
    )
    c3.metric(
        "Akurasi Kapten",
        f"{cap_analysis['optimal_rate']}%",
        f"{sum(1 for d in details if d['was_optimal'])}/{len(details)} GW optimal",
    )

    # Captain detail table
    cap_rows = '<div class="fpl-card"><div style="display:flex;flex-direction:column;gap:6px">'
    for d in details:
        check = "✅" if d["was_optimal"] else "❌"
        missed_txt = "" if d["was_optimal"] else f' <span style="color:#dc2626">(optimal: {esc(d["optimal_name"])} {d["optimal_pts"]} pts, missed {d["missed_pts"]:+.0f})</span>'
        cap_rows += (
            f'<div style="display:flex;align-items:center;gap:8px;font-size:.8rem;padding:4px 0;border-bottom:1px solid #f1f5f9">'
            f'<span style="min-width:50px;color:#64748b">GW {d["gw"]}</span>'
            f'<span>{check}</span>'
            f'<span style="font-weight:500;min-width:120px">{esc(d["captain_name"])}</span>'
            f'<span style="color:#37003c;min-width:50px">{d["captain_pts"]} pts</span>'
            f'{missed_txt}'
            f'</div>'
        )
    cap_rows += '</div></div>'
    st.markdown(cap_rows, unsafe_allow_html=True)
else:
    st.info("Data kapten belum tersedia.")

# --- Points on Bench ---
st.markdown('<div class="section" style="font-size:.95rem">🪑 Poin <em>di Bench</em> per GW</div>', unsafe_allow_html=True)

bench_pts = [g["points_on_bench"] for g in gw_results]
fig_bench = go.Figure()
fig_bench.add_trace(go.Bar(
    x=gw_nums, y=bench_pts, name="Poin di Bench",
    marker_color=["#dc2626" if b >= 10 else "#f59e0b" if b >= 5 else "#94a3b8" for b in bench_pts],
    text=bench_pts, textposition="outside",
))
fig_bench.update_layout(
    xaxis_title="Gameweek", yaxis_title="Poin di Bench",
    height=250,
    paper_bgcolor="#fff", plot_bgcolor="#f8f9fb",
    font=dict(color="#1a1a2e", size=11),
    margin=dict(l=10, r=10, t=10, b=10),
)
st.plotly_chart(fig_bench, use_container_width=True)
st.caption("Merah = 10+ poin di bench (bench pain parah). Kuning = 5-9 poin. Abu-abu = normal.")

st.divider()
st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem'>"
    "Data diambil dari FPL API publik. Analisis kapten optimal menggunakan skor aktual per GW. "
    "Semua statistik dihitung dari data resmi FPL.</p>",
    unsafe_allow_html=True,
)
