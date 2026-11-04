"""Simple, action-first UI helpers.

The goal is to answer "what should I do?" before showing model internals.
Advanced numbers stay available through the Analis mode and detail expanders.
"""

from __future__ import annotations

import html

import streamlit as st

ACTION_CSS = """
<style>
/* ── Action-first cards ─────────────────────────────── */
.action-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-left: 5px solid #37003c;
  border-radius: 12px;
  padding: 16px 18px;
  height: 100%;
  box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.action-card.tone-good { border-left-color: #15803d; }
.action-card.tone-warn { border-left-color: #d97706; }
.action-card.tone-bad { border-left-color: #dc2626; }
.action-card.tone-info { border-left-color: #4f46e5; }
.ac-kicker { font-size: .64rem; text-transform: uppercase; letter-spacing: 1.1px; color: #64748b; font-weight: 700; }
.ac-headline { font-size: 1.02rem; font-weight: 700; color: #0f172a; margin: 5px 0 4px; line-height: 1.25; }
.ac-metric { font-size: 1.55rem; font-weight: 700; color: #37003c; line-height: 1.1; margin: 4px 0 2px; }
.ac-metric small { font-size: .72rem; font-weight: 500; color: #64748b; }
.ac-meaning { font-size: .78rem; color: #475569; line-height: 1.45; margin-top: 6px; }
.ac-footer { font-size: .7rem; color: #94a3b8; margin-top: 10px; }
.confidence {
  display: inline-block; padding: 2px 9px; border-radius: 99px;
  font-size: .62rem; font-weight: 700; letter-spacing: .4px;
  text-transform: uppercase;
}
.confidence-high { background: #dcfce7; color: #166534; }
.confidence-medium { background: #fef3c7; color: #92400e; }
.confidence-low { background: #fee2e2; color: #991b1b; }
.status-pill {
  display: inline-block; padding: 2px 9px; border-radius: 99px;
  font-size: .65rem; font-weight: 600;
}
.status-good { background: #dcfce7; color: #166534; }
.status-warn { background: #fef3c7; color: #92400e; }
.status-bad { background: #fee2e2; color: #991b1b; }
.status-info { background: #e0e7ff; color: #3730a3; }
.simple-hero {
  background: linear-gradient(135deg, #37003c 0%, #5b0a63 100%);
  border-radius: 14px; padding: 20px 24px; color: #fff; margin-bottom: 14px;
}
.simple-hero .k { font-size: .66rem; letter-spacing: 1.4px; text-transform: uppercase; color: #d8b4fe; font-weight: 700; }
.simple-hero h1 { margin: 4px 0 2px; font-size: 1.55rem; color: #fff !important; }
.simple-hero p { margin: 0; font-size: .82rem; color: #e9d5ff; }
.glossary-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
  padding: 12px 14px; margin-bottom: 8px;
}
.glossary-card b { color: #37003c; }
.glossary-card span { color: #475569; font-size: .82rem; }
.simple-note {
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
  padding: 10px 14px; color: #475569; font-size: .78rem;
}
</style>
"""


def inject_styles():
    st.markdown(ACTION_CSS, unsafe_allow_html=True)


def is_beginner():
    return st.session_state.get("ui_mode", "Pemula") == "Pemula"


def _sidebar_link(page, label, **kwargs):
    try:
        st.sidebar.page_link(page, label=label, **kwargs)
        return True
    except Exception:
        return False


def ui_mode_toggle():
    """Simple sidebar: five main menus + display mode + advanced links."""
    if "ui_mode" not in st.session_state:
        st.session_state["ui_mode"] = "Pemula"

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='font-size:.72rem;font-weight:700;letter-spacing:1.2px;"
        "text-transform:uppercase;color:#37003c;margin-bottom:6px'>Menu</div>",
        unsafe_allow_html=True,
    )
    _sidebar_link("app.py", "🏠 Minggu Ini", use_container_width=True)
    _sidebar_link("pages/3_Skuad_Saya.py", "👥 Skuad Saya", use_container_width=True)
    _sidebar_link("pages/1_Cari_Pemain.py", "🔎 Cari Pemain", use_container_width=True)
    _sidebar_link("pages/5_Performa.py", "📈 Performa", use_container_width=True)
    _sidebar_link("pages/4_Chip_dan_Lab.py", "🧪 Lab & Chip", use_container_width=True)

    with st.sidebar.expander("Lainnya"):
        _sidebar_link("pages/0_Rencana_Detail.py", "📋 Rencana Detail")
        _sidebar_link("pages/2_Kapten_dan_Transfer.py", "🎯 Kapten & Transfer")
        _sidebar_link("pages/6_Riwayat_GW.py", "📜 Riwayat GW")
        _sidebar_link("pages/7_Kamus.py", "📖 Kamus FPL")

    st.sidebar.markdown("---")
    st.sidebar.radio(
        "Tampilan",
        options=["Pemula", "Analis"],
        key="ui_mode",
        horizontal=True,
        help="Pemula menyembunyikan angka teknis. Analis menampilkan semua metrik.",
    )
    st.sidebar.caption(
        "Pemula: keputusan + alasan singkat. Analis: EV, p10–p90, xGI, DefCon, dan detail model."
    )


def esc(value):
    return html.escape(str(value))


def confidence_badge(level):
    level = str(level or "Sedang")
    cls = {"Tinggi": "confidence-high", "Sedang": "confidence-medium", "Rendah": "confidence-low"}.get(level, "confidence-medium")
    return f'<span class="confidence {cls}">Keyakinan: {esc(level)}</span>'


def status_pill(text, tone="info"):
    cls = {"good": "status-good", "warn": "status-warn", "bad": "status-bad"}.get(tone, "status-info")
    return f'<span class="status-pill {cls}">{esc(text)}</span>'


def simple_hero(title, subtitle="", kicker="FPL · Keputusan Minggu Ini"):
    st.markdown(
        f"""
        <div class="simple-hero">
          <div class="k">{esc(kicker)}</div>
          <h1>{esc(title)}</h1>
          <p>{esc(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def action_card(title, headline, metric=None, metric_label=None, meaning="",
                confidence=None, tone="info", footer=""):
    """Render one large, plain-language decision card."""
    metric_html = ""
    if metric is not None:
        label = f"<small>{esc(metric_label)}</small>" if metric_label else ""
        metric_html = f'<div class="ac-metric">{esc(metric)} {label}</div>'
    conf = confidence_badge(confidence) if confidence else ""
    st.markdown(
        f"""
        <div class="action-card tone-{esc(tone)}">
          <div class="ac-kicker">{esc(title)}</div>
          <div class="ac-headline">{esc(headline)}</div>
          {metric_html}
          <div class="ac-meaning">{esc(meaning)}</div>
          <div style="margin-top:8px">{conf}</div>
          <div class="ac-footer">{esc(footer)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def simple_note(text):
    st.markdown(f'<div class="simple-note">{text}</div>', unsafe_allow_html=True)


def section(title, subtitle=None):
    st.markdown(f'<div class="section">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def why_expander(title, lines):
    """Plain-language explanation block."""
    with st.expander(f"💡 {title}"):
        for line in lines:
            if line:
                st.write(f"- {line}")


GLOSSARY = [
    ("Proyeksi / EV / xP", "Perkiraan poin rata-rata. Bukan jaminan; bisa meleset sekitar 1–2 poin."),
    ("p10–p90", "Rentang realistis. 80% hasil biasanya berada di antara dua angka ini."),
    ("Peluang main", "Kemungkinan pemain bermain, dari status resmi FPL."),
    ("Risiko blank", "Peluang pemain tidak bermain sama sekali."),
    ("Haul", "Ledakan poin, biasanya 10+ poin."),
    ("FDR", "Tingkat kesulitan lawan: 1 = mudah, 5 = sulit."),
    ("xGI", "Peluang terlibat gol (gol atau assist) per 90 menit."),
    ("DefCon", "Bonus +2 dari aksi bertahan (tackle, intercept, clearance, dll.)."),
    ("CS / Clean Sheet", "Peluang tim tidak kebobolan."),
    ("FT", "Free transfer / transfer gratis."),
    ("Hit", "Penalti -4 poin untuk transfer ekstra."),
    ("TC / BB / WC / FH", "Triple Captain / Bench Boost / Wildcard / Free Hit."),
    ("DGW / BGW", "Double Gameweek (2 laga) / Blank Gameweek (tidak bermain)."),
    ("MAE", "Rata-rata meleset berapa poin dari hasil aktual."),
    ("Top-K", "Akurasi untuk 10/20 pemain teratas — yang biasanya dipilih."),
    ("Kalibrasi", "Apakah model terlalu tinggi atau terlalu rendah secara sistematis."),
    ("Backtest", "Uji model memakai data Gameweek yang sudah selesai."),
    ("Mode Pemula", "Menyembunyikan angka teknis dan menampilkan keputusan + alasan."),
    ("Mode Analis", "Menampilkan semua metrik, grafik, dan alat eksperimen."),
]


def glossary_cards(filter_text=""):
    q = (filter_text or "").strip().lower()
    for term, meaning in GLOSSARY:
        if q and q not in term.lower() and q not in meaning.lower():
            continue
        st.markdown(
            f'<div class="glossary-card"><b>{esc(term)}</b><br><span>{esc(meaning)}</span></div>',
            unsafe_allow_html=True,
        )
