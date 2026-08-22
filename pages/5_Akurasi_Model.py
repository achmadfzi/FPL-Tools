import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fpl.accuracy import compute_accuracy, history, suggested_weights
from fpl.ui import apply_theme, autorefresh, esc, load_data

st.set_page_config(page_title="Akurasi Model", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event

st.markdown('<div class="section">Akurasi <em>Model</em> Proyeksi</div>', unsafe_allow_html=True)
st.caption(
    "Evaluasi seberapa akurat model proyeksi dibanding skor aktual FPL. "
    "Proyeksi disimpan otomatis setiap GW. Setelah GW selesai, skor aktual diambil dari API FPL."
)

# Try to compute accuracy for past GWs that have actuals
hist = history()

# Auto-compute accuracy for any GW that has projections but not yet metrics
for h in hist:
    if h["has_projections"] and not h["metrics"]:
        compute_accuracy(h["gw"])

# Reload after potential computation
hist = history()
completed = [h for h in hist if h["metrics"] is not None]

if not completed:
    st.info(
        "Belum ada data akurasi. Sistem akan otomatis menyimpan proyeksi setiap GW. "
        "Setelah GW selesai dan data aktual tersedia, akurasi akan dihitung secara otomatis."
    )
    st.markdown(
        """
        <div class="fpl-card">
          <h3>Cara Kerja Accuracy Tracking</h3>
          <div class="info-line">1. Sebelum deadline → proyeksi per pemain disimpan otomatis</div>
          <div class="info-line">2. Setelah GW selesai → skor aktual diambil dari API FPL</div>
          <div class="info-line">3. Dihitung MAE (Mean Absolute Error) dan RMSE per posisi & FDR</div>
          <div class="info-line">4. Setelah 3+ GW → sistem suggest penyesuaian bobot model</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    # --- Summary Metrics ---
    c1, c2, c3, c4 = st.columns(4)
    maes = [h["metrics"]["mae"] for h in completed]
    rmses = [h["metrics"]["rmse"] for h in completed]
    avg_mae = sum(maes) / len(maes)
    avg_rmse = sum(rmses) / len(rmses)
    latest = completed[-1]
    c1.metric("MAE Rata-rata", f"{avg_mae:.2f}", f"{len(completed)} GW data")
    c2.metric("RMSE Rata-rata", f"{avg_rmse:.2f}")
    c3.metric("MAE Terakhir", f"{latest['metrics']['mae']:.2f}", f"GW {latest['gw']}")
    c4.metric("GW Terevaluasi", f"{len(completed)}", f"dari {len(hist)} tersimpan")

    # --- Trend Chart ---
    st.markdown('<div class="section" style="font-size:.95rem">Tren <em>Akurasi</em> Sepanjang Musim</div>', unsafe_allow_html=True)
    fig = go.Figure()
    gws = [h["gw"] for h in completed]
    fig.add_trace(go.Scatter(
        x=gws, y=maes, mode="lines+markers", name="MAE",
        line=dict(color="#37003c", width=3), marker=dict(size=8, color="#37003c"),
    ))
    fig.add_trace(go.Scatter(
        x=gws, y=rmses, mode="lines+markers", name="RMSE",
        line=dict(color="#f59e0b", width=2, dash="dash"), marker=dict(size=6, color="#f59e0b"),
    ))
    fig.update_layout(
        xaxis_title="Gameweek", yaxis_title="Error",
        height=350,
        paper_bgcolor="#fff", plot_bgcolor="#f8f9fb",
        font=dict(color="#1a1a2e", size=11),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("MAE = rata-rata selisih absolut proyeksi vs aktual. RMSE = akar rata-rata kuadrat error (lebih sensitif terhadap error besar).")

    # --- Per GW Table ---
    st.markdown('<div class="section" style="font-size:.95rem">Detail <em>Per Gameweek</em></div>', unsafe_allow_html=True)
    rows = []
    for h in completed:
        m = h["metrics"]
        rows.append({
            "GW": h["gw"],
            "MAE": m["mae"],
            "RMSE": m["rmse"],
            "N Pemain": m["n"],
            "MAE GK": m.get("by_pos", {}).get("GK", "-"),
            "MAE DEF": m.get("by_pos", {}).get("DEF", "-"),
            "MAE MID": m.get("by_pos", {}).get("MID", "-"),
            "MAE FWD": m.get("by_pos", {}).get("FWD", "-"),
        })
    acc_df = pd.DataFrame(rows)
    styled_acc = (
        acc_df.style
        .map(lambda v: "color:#0f172a;font-weight:400;text-align:center")
        .format({"MAE": "{:.2f}", "RMSE": "{:.2f}"})
        .hide(axis="index")
    )
    st.dataframe(styled_acc, use_container_width=True, hide_index=True)

    # --- Breakdown by Position ---
    st.markdown('<div class="section" style="font-size:.95rem">Akurasi <em>Per Posisi</em></div>', unsafe_allow_html=True)
    pos_data = {}
    for h in completed:
        for pos, mae in h["metrics"].get("by_pos", {}).items():
            pos_data.setdefault(pos, []).append(mae)
    if pos_data:
        pos_cols = st.columns(len(pos_data))
        for col, (pos, maes_list) in zip(pos_cols, sorted(pos_data.items())):
            avg = sum(maes_list) / len(maes_list)
            col.metric(pos, f"MAE {avg:.2f}", f"{len(maes_list)} GW data")

    # --- Breakdown by FDR ---
    st.markdown('<div class="section" style="font-size:.95rem">Akurasi <em>Per FDR</em></div>', unsafe_allow_html=True)
    fdr_data = {}
    for h in completed:
        for fdr, mae in h["metrics"].get("by_fdr", {}).items():
            fdr_data.setdefault(fdr, []).append(mae)
    if fdr_data:
        fdr_cols = st.columns(min(len(fdr_data), 5))
        fdr_labels = {"1": "Sangat Mudah", "2": "Mudah", "3": "Sedang", "4": "Sulit", "5": "Sangat Sulit"}
        for col, (fdr, maes_list) in zip(fdr_cols, sorted(fdr_data.items())):
            avg = sum(maes_list) / len(maes_list)
            col.metric(f"FDR {fdr}", f"MAE {avg:.2f}", fdr_labels.get(fdr, ""))

    # --- Latest GW Detail ---
    st.markdown('<div class="section" style="font-size:.95rem">Detail <em>GW Terakhir</em></div>', unsafe_allow_html=True)
    m = latest["metrics"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="fpl-card"><h3>Top 5 Over-Estimate</h3><div class="card-sub">Proyeksi terlalu tinggi vs aktual</div>', unsafe_allow_html=True)
        for e in m.get("top_overestimate", []):
            st.markdown(
                f"<div class='info-line'><span style='color:#b91c1c;font-weight:500'>{esc(e['name'])}</span> "
                f"<span style='color:#64748b'>({e['pos']}) — proyeksi {e['proj']:.2f} vs aktual {e['actual']} "
                f"(error {e['error']:+.2f})</span></div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="fpl-card"><h3>Top 5 Under-Estimate</h3><div class="card-sub">Proyeksi terlalu rendah vs aktual</div>', unsafe_allow_html=True)
        for e in m.get("top_underestimate", []):
            st.markdown(
                f"<div class='info-line'><span style='color:#15803d;font-weight:500'>{esc(e['name'])}</span> "
                f"<span style='color:#64748b'>({e['pos']}) — proyeksi {e['proj']:.2f} vs aktual {e['actual']} "
                f"(error {e['error']:+.2f})</span></div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Suggested Weights ---
    st.markdown('<div class="section" style="font-size:.95rem">Saran <em>Penyesuaian</em> Model</div>', unsafe_allow_html=True)
    sw = suggested_weights()
    if sw["status"] == "insufficient_data":
        st.info(sw["message"])
    else:
        st.markdown(
            f"""
            <div class="fpl-card">
              <h3>Analisis {sw['n_gws']} Gameweek</h3>
              <div class="info-line">MAE rata-rata: <b style="color:#37003c">{sw['avg_mae']:.2f}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if sw.get("suggestions"):
            for s in sw["suggestions"]:
                st.warning(s)
        else:
            st.success("Model sudah cukup baik — tidak ada saran penyesuaian saat ini.")

        with st.expander("Detail MAE per posisi & FDR"):
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Per Posisi:**")
                for pos, mae in sorted(sw.get("by_pos", {}).items()):
                    st.write(f"  {pos}: MAE {mae:.2f}")
            with c2:
                st.write("**Per FDR:**")
                for fdr, mae in sorted(sw.get("by_fdr", {}).items()):
                    st.write(f"  FDR {fdr}: MAE {mae:.2f}")

st.divider()
st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem'>"
    "Evaluasi dilakukan otomatis setelah setiap Gameweek selesai. Proyeksi disimpan sebelum deadline, "
    "skor aktual diambil dari FPL Live API. Model baru bermakna setelah 3-5 GW data terkumpul.</p>",
    unsafe_allow_html=True,
)
