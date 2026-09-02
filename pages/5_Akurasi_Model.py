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

# =============================================================================
# ADAPTIVE WEIGHTS SECTION
# =============================================================================
st.markdown('<div class="section">🔧 Adaptive <em>Weights</em> — Optimasi Bobot Model</div>', unsafe_allow_html=True)
st.caption(
    "Optimasi otomatis bobot model proyeksi berdasarkan error historis. "
    "Grid search mencari kombinasi bobot yang meminimalkan MAE pada data GW lalu."
)

try:
    from fpl.adaptive import (
        DEFAULT_WEIGHTS,
        compare_weights,
        load_tuned_weights,
        optimize_weights,
        save_tuned_weights,
    )

    tuned = load_tuned_weights()

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🔧 Optimalkan Bobot", use_container_width=True):
            progress_bar = st.progress(0, text="Mencari bobot optimal...")

            def update_progress(pct):
                progress_bar.progress(pct, text=f"Grid search {pct:.0%}...")

            result = optimize_weights(progress_callback=update_progress)
            progress_bar.empty()

            if result["status"] == "insufficient_data":
                st.warning(result["message"])
            else:
                saved = save_tuned_weights(result["weights"], {
                    "default_mae": result["default_mae"],
                    "tuned_mae": result["tuned_mae"],
                    "improvement_pct": result["improvement_pct"],
                    "n_samples": result["n_samples"],
                    "enabled": True,
                })
                st.success(
                    f"Bobot optimal ditemukan! MAE: {result['default_mae']:.3f} → {result['tuned_mae']:.3f} "
                    f"(improvement {result['improvement_pct']:+.1f}%). {result['n_combos_tested']} kombinasi diuji."
                )
                st.rerun()

    with c2:
        if tuned and tuned.get("weights"):
            metrics = tuned.get("metrics", {})
            is_enabled = metrics.get("enabled", False)
            if st.toggle("Gunakan bobot yang sudah di-tune", value=is_enabled, key="use_tuned"):
                if not is_enabled:
                    metrics["enabled"] = True
                    save_tuned_weights(tuned["weights"], metrics)
                    st.toast("Bobot tuned diaktifkan! Refresh data untuk menerapkan.", icon="✅")
                    st.rerun()
            else:
                if is_enabled:
                    metrics["enabled"] = False
                    save_tuned_weights(tuned["weights"], metrics)
                    st.toast("Kembali ke bobot default.", icon="↩️")
                    st.rerun()

    if tuned and tuned.get("weights"):
        metrics = tuned.get("metrics", {})
        status_icon = "🟢" if metrics.get("enabled") else "⚪"
        st.markdown(
            f"""
            <div class="fpl-card">
              <h3>{status_icon} Bobot Tuned {'(Aktif)' if metrics.get('enabled') else '(Nonaktif)'}</h3>
              <div class="info-line">MAE Default: <b>{metrics.get('default_mae', '-')}</b> → Tuned: <b style="color:#15803d">{metrics.get('tuned_mae', '-')}</b></div>
              <div class="info-line">Improvement: <b style="color:#37003c">{metrics.get('improvement_pct', 0):+.1f}%</b> | Data: {metrics.get('n_samples', 0)} sample</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Comparison table
        with st.expander("📊 Perbandingan Bobot Default vs Tuned"):
            comparison = compare_weights(DEFAULT_WEIGHTS, tuned["weights"])
            comp_df = pd.DataFrame(comparison)
            display_cols = ["param", "default", "tuned", "change"]
            styled = (
                comp_df[display_cols].style
                .map(lambda v: "color:#15803d;font-weight:500" if isinstance(v, (int, float)) and v > 0
                     else ("color:#dc2626;font-weight:500" if isinstance(v, (int, float)) and v < 0 else ""),
                     subset=["change"])
                .format({"default": "{:.3f}", "tuned": "{:.3f}", "change": "{:+.3f}"})
                .hide(axis="index")
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.info(
            "Belum ada bobot yang di-tune. Klik 'Optimalkan Bobot' untuk memulai grid search. "
            "Membutuhkan minimal 2 GW data lengkap (proyeksi + aktual)."
        )
except Exception as e:
    st.warning(f"Modul adaptive weights belum tersedia: {e}")

# =============================================================================
# ML MODEL SECTION
# =============================================================================
st.markdown('<div class="section">🤖 Machine Learning <em>xP Model</em></div>', unsafe_allow_html=True)
st.caption(
    "Model ML (Gradient Boosting) yang belajar dari error historis untuk meningkatkan akurasi proyeksi. "
    "Ditraining dari data GW yang sudah selesai."
)

try:
    from fpl.ml_model import model_status, train_model

    status = model_status()

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🤖 Train ML Model", use_container_width=True):
            with st.spinner("Training model ML..."):
                result = train_model()

            if result["status"] == "insufficient_data":
                st.warning(result["message"])
            else:
                st.success(
                    f"Model ML berhasil di-train! {result['n_samples']} sample. "
                    f"GBR MAE: {result['gbr_mae']:.3f} vs Formula MAE: {result['formula_mae']:.3f} "
                    f"(improvement {result['improvement_pct']:+.1f}%)"
                )
                st.rerun()

    with c2:
        if status["available"]:
            st.markdown(
                f"""
                <div style="display:flex;gap:16px;align-items:center;padding:8px 0">
                  <span style="font-size:1.2rem">🟢</span>
                  <div>
                    <div style="font-weight:600;color:#15803d">Model ML Aktif</div>
                    <div style="font-size:.8rem;color:#64748b">{status['n_samples']} training samples</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if status["available"]:
        c1, c2, c3 = st.columns(3)
        c1.metric("Formula MAE", f"{status['formula_mae']:.3f}", "baseline")
        c2.metric("ML (GBR) MAE", f"{status['gbr_mae']:.3f}",
                   f"{status['improvement_pct']:+.1f}%",
                   delta_color="inverse" if status["improvement_pct"] > 0 else "normal")
        c3.metric("Training Samples", status["n_samples"])

        # Feature importance chart
        importances = status.get("importances", {})
        if importances:
            st.markdown('<div class="section" style="font-size:.85rem">Feature <em>Importance</em></div>', unsafe_allow_html=True)
            sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)
            names = [x[0] for x in sorted_imp]
            values = [x[1] for x in sorted_imp]

            fig_imp = go.Figure()
            fig_imp.add_trace(go.Bar(
                y=names, x=values,
                orientation="h",
                marker_color="#37003c",
            ))
            fig_imp.update_layout(
                height=max(200, len(names) * 28),
                paper_bgcolor="#fff", plot_bgcolor="#f8f9fb",
                font=dict(color="#1a1a2e", size=11),
                margin=dict(l=10, r=10, t=10, b=10),
                yaxis=dict(autorange="reversed"),
                xaxis_title="Importance",
            )
            st.plotly_chart(fig_imp, use_container_width=True)
            st.caption(
                "Feature importance menunjukkan fitur mana yang paling berpengaruh dalam prediksi ML. "
                "Semakin tinggi = semakin penting."
            )
    else:
        st.info(status.get("message", "Model ML belum di-train."))

except Exception as e:
    st.warning(f"Modul ML belum tersedia: {e}")

st.divider()
st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem'>"
    "Evaluasi dilakukan otomatis setelah setiap Gameweek selesai. Proyeksi disimpan sebelum deadline, "
    "skor aktual diambil dari FPL Live API. Model baru bermakna setelah 3-5 GW data terkumpul.</p>",
    unsafe_allow_html=True,
)
