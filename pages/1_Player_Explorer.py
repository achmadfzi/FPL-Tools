import plotly.graph_objects as go
import streamlit as st

from fpl.api import get_element_summary
from fpl.optimizer import fixture_line, projection_explanation
from fpl.ui import (
    apply_theme,
    autorefresh,
    bar,
    esc,
    fdr_badge_html,
    load_data,
    photo_url,
    player_img_html,
    pos_badge_html,
    status_badge_html,
)
from fpl.utils import fmt_price

st.set_page_config(page_title="Player Explorer", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()

from fpl.paststats import attach, indicator as past_indicator, load as load_past

with st.spinner("Memuat statistik musim lalu..."):
    df = attach(df, load_past(gd))

st.markdown('<div class="section">Player <em>Explorer</em></div>', unsafe_allow_html=True)
st.caption("Jelajahi semua pemain, filter, dan lihat detail proyeksi poin.")

c1, c2, c3, c4 = st.columns(4)
with c1:
    pos_filter = st.multiselect("Posisi", ["GK", "DEF", "MID", "FWD"], default=None, placeholder="Semua posisi")
with c2:
    team_filter = st.multiselect("Tim", sorted(df["team_short"].unique()), default=None, placeholder="Semua tim")
with c3:
    max_price = st.slider("Harga maksimal (£juta)", 4.0, 15.0, 15.0, 0.5)
with c4:
    status_filter = st.selectbox("Status", ["Semua", "Tersedia", "Cedera", "Diragukan", "Tidak Tersedia"])

c_last, c_spacer = st.columns([1, 3])
with c_last:
    last_filter = st.selectbox(
        "Acuan musim lalu",
        ["Semua", "Bintang (≥200 poin)", "Sangat baik (≥150)", "Baik (≥100)", "Tanpa riwayat poin"],
    )

view = df.copy()
if pos_filter:
    view = view[view["pos"].isin(pos_filter)]
if team_filter:
    view = view[view["team_short"].isin(team_filter)]
view = view[view["price"] <= max_price * 10]
if status_filter == "Tersedia":
    view = view[view["status"] == "a"]
elif status_filter == "Cedera":
    view = view[view["status"] == "i"]
elif status_filter == "Diragukan":
    view = view[view["status"] == "d"]
elif status_filter == "Tidak Tersedia":
    view = view[view["status"].isin(["u", "n"])]
if last_filter == "Bintang (≥200 poin)":
    view = view[view["last_points"] >= 200]
elif last_filter == "Sangat baik (≥150)":
    view = view[view["last_points"] >= 150]
elif last_filter == "Baik (≥100)":
    view = view[view["last_points"] >= 100]
elif last_filter == "Tanpa riwayat poin":
    view = view[view["last_points"] == 0]

c1, c2 = st.columns([2, 1])
with c1:
    sort_options = ["proj", "form", "ppg", "xGI_per90", "selected_by", "price", "last_points", "last_value", "last_ppg"]
    if "ml_proj" in view.columns and view["ml_proj"].notna().any():
        sort_options.insert(1, "ml_proj")
    sort_col = st.selectbox(
        "Urutkan berdasarkan",
        sort_options,
        format_func=lambda c: {
            "proj": "Proyeksi poin GW ini",
            "form": "Form (5 GW)",
            "ppg": "Poin per game",
            "xGI_per90": "xGI per 90 menit",
            "selected_by": "Kepemilikan %",
            "price": "Harga",
            "last_points": "Poin musim lalu",
            "last_value": "Value musim lalu (poin/£1jt)",
            "last_ppg": "PPG musim lalu",
            "ml_proj": "ML Proyeksi (AI)",
        }.get(c, c),
    )
with c2:
    ascending = st.checkbox("Urutkan naik", value=False)

view = view.sort_values(sort_col, ascending=ascending)

# Build display table
has_ml = "ml_proj" in view.columns and view["ml_proj"].notna().any()
cols = ["web_name", "team_short", "pos", "price", "proj"]
if has_ml:
    cols.append("ml_proj")
cols += ["xGI_per90", "last_points", "last_ppg", "form", "ppg", "selected_by", "opponent_short", "fdr", "chance", "status"]

show = view[cols].copy()
show["price"] = show["price"] / 10
col_names = ["Pemain", "Tim", "Pos", "Harga", "Proyeksi"]
if has_ml:
    col_names.append("ML Proj")
col_names += ["xGI/90", "Poin Lalu", "PPG Lalu", "Form", "PPG", "Kepemilikan", "Lawan", "FDR", "Peluang", "Status"]
show.columns = col_names


def style_pos(v):
    colors = {
        "GK": "background-color:#d97706;color:#ffffff;font-weight:600;text-align:center",
        "DEF": "background-color:#2563eb;color:#ffffff;font-weight:600;text-align:center",
        "MID": "background-color:#16a34a;color:#ffffff;font-weight:600;text-align:center",
        "FWD": "background-color:#dc2626;color:#ffffff;font-weight:600;text-align:center",
    }
    return colors.get(v, "color:#0f172a;text-align:center")


def style_fdr(v):
    try:
        iv = int(float(v))
    except (ValueError, TypeError):
        iv = 3
    colors = {
        1: "background-color:#01FC7A;color:#064420;font-weight:600;text-align:center",
        2: "background-color:#01FC7A;color:#064420;font-weight:600;text-align:center",
        3: "background-color:#e2e8f0;color:#1e293b;font-weight:600;text-align:center",
        4: "background-color:#FF1751;color:#ffffff;font-weight:600;text-align:center",
        5: "background-color:#80072D;color:#ffffff;font-weight:600;text-align:center",
    }
    return colors.get(iv, "color:#0f172a;text-align:center")


def style_status(v):
    c = "#16a34a" if v == "a" else "#dc2626"
    return f"color:{c};font-weight:600;text-align:center"


def fmt_fdr(v):
    try:
        return f"{int(float(v))}"
    except (ValueError, TypeError):
        return "-"


def fmt_chance(v):
    try:
        f = float(v)
        if f <= 1.0:
            return f"{int(f * 100)}%"
        return f"{int(f)}%"
    except (ValueError, TypeError):
        return "-"


style_subsets = ["Pemain", "Tim", "xGI/90", "PPG Lalu", "Form", "PPG", "Kepemilikan", "Lawan", "Peluang"]
proj_subsets = ["Proyeksi"]
format_dict = {
    "Harga": "£{:.1f}m",
    "Proyeksi": "{:.2f}",
    "xGI/90": "{:.2f}",
    "Poin Lalu": "{:.0f}",
    "PPG Lalu": "{:.2f}",
    "Form": "{:.2f}",
    "PPG": "{:.2f}",
    "Kepemilikan": "{:.1f}%",
    "FDR": fmt_fdr,
    "Peluang": fmt_chance,
}
if has_ml:
    format_dict["ML Proj"] = "{:.2f}"
    proj_subsets.append("ML Proj")

styled = (
    show.style
    .map(lambda v: "color:#0f172a;font-weight:400", subset=style_subsets)
    .map(lambda v: "color:#64748b;font-weight:400", subset=["Harga"])
    .map(style_pos, subset=["Pos"])
    .map(style_fdr, subset=["FDR"])
    .map(style_status, subset=["Status"])
    .map(lambda v: "color:#d97706;font-weight:500", subset=["Poin Lalu"])
    .map(lambda v: "color:#37003c;font-weight:600", subset=proj_subsets)
    .format(format_dict)
    .hide(axis="index")
)

st.dataframe(styled, use_container_width=True, height=520, hide_index=True)

st.divider()

names = view.sort_values("proj", ascending=False)
options = {f"{r['web_name']} ({r['team_short']}, {r['pos']}, {fmt_price(r['price'])})": r["id"] for _, r in names.iterrows()}
sel = st.selectbox("Pilih pemain untuk melihat detail proyeksi", list(options.keys()))
pid = options[sel]
row = df[df["id"] == pid].iloc[0]

c1, c2 = st.columns([2, 3])
with c1:
    st.markdown(
        f"""
        <div class="fpl-card" style="text-align:center">
          {player_img_html(row, style="width:96px;height:120px;object-fit:contain;background:#f5f6f8;border-radius:12px")}
          <h3 style="margin:10px 0 2px">{esc(row['web_name'])}</h3>
          <div>{esc(row['team_name'])} {pos_badge_html(row['pos'])}</div>
          <div class="p-team" style="margin:8px 0">{fmt_price(row['price'])} {status_badge_html(row['status'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if row["news"]:
        st.markdown(f'<div class="news-warn">{esc(row["news"])}</div>', unsafe_allow_html=True)
    with st.expander("Cara menghitung proyeksi"):
        st.code(projection_explanation(row))
with c2:
    st.markdown(
        f"""
        <div class="fpl-card">
          <h3>Proyeksi Gameweek Ini</h3>
          {bar("Estimasi dasar (form)", row['own'], 5.0, '#6d28d9')}
          {bar("Proyeksi resmi FPL", row['ep_next_fpl'], 5.0, '#2563eb')}
          {bar("Proyeksi akhir", row['proj'] if row['proj'] else 0, 8.0, '#37003c')}
          <div class="card-sub" style="margin-top:10px">{fixture_line(row)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    info = [
        f"<div class='info-line'>Kepemilikan: <b>{row['selected_by']:.1f}%</b></div>",
        f"<div class='info-line'>Menit bermain: <b>{row['minutes']}</b> | Starter: <b>{row['starts']}</b></div>",
        f"<div class='info-line'>Poin total: <b>{row['total_points']}</b> | Form: <b>{row['form']:.2f}</b> | PPG: <b>{row['ppg']:.2f}</b></div>",
        f"<div class='info-line'>xGI: <b>{row['xGI']:.2f}</b> | xGI/90: <b style='color:#6d28d9'>{row['xGI_per90']:.2f}</b> | xG: <b>{row['xG']:.2f}</b> | xA: <b>{row['xA']:.2f}</b></div>",
        f"<div class='info-line'>Threat: <b>{row['threat']:.0f}</b> | CS prob: <b style='color:#2563eb'>{row.get('cs_prob', 0):.1%}</b></div>",
    ]
    if row["last_points"]:
        star = "" if row["last_points"] < 200 else " · <b style='color:#d97706'>BINTANG MUSIM LALU</b>"
        info.append(
            f"<div class='info-line'>Musim lalu: <b style='color:#d97706'>{int(row['last_points'])} poin</b> "
            f"(ppg {row['last_ppg']:.2f}) · G {int(row['last_goals'])} · A {int(row['last_assists'])} · "
            f"CS {int(row['last_cs'])} · Bonus {int(row['last_bonus'])} · value {row['last_value']:.2f} pts/£1jt{star}</div>"
        )
    if row["price_change"]:
        info.append(f"<div class='info-line'>Perubahan harga: <b>{row['price_change'] / 10:+.1f}m</b></div>")

    try:
        summary = get_element_summary(pid)
        hp = summary.get("history_past") or []
        if hp:
            s = hp[-1]
            m, sts = int(s.get("minutes") or 0), int(s.get("starts") or 0)
            from fpl.reliability import factor as rel_factor, label as rel_label

            f = rel_factor(m, True, row["selected_by"])
            warn = "" if f >= 1.0 else f" (proyeksi dikurangi x{f:.2f} karena risiko menit)"
            info.append(
                f"<div class='info-line'>Menit musim lalu: <b>{m}</b> ({sts} starter) · "
                f"<b style='color:{'#16a34a' if f >= 0.88 else '#d97706'}'>{rel_label(m, True, row['selected_by'])}</b>{warn}</div>"
            )
        else:
            from fpl.reliability import factor as rel_factor, label as rel_label

            f = rel_factor(0, False, row["selected_by"])
            trust = f >= 0.95
            info.append(
                f"<div class='info-line'>Musim lalu: <b style='color:{'#16a34a' if trust else '#d97706'}'>{rel_label(0, False, row['selected_by'])}</b> "
                f"(kepemilikan komunitas {row['selected_by']:.1f}% → faktor x{f:.2f})</div>"
            )
    except Exception:
        pass
    st.markdown(f'<div class="fpl-card">{"".join(info)}</div>', unsafe_allow_html=True)

    st.markdown('<div class="section" style="font-size:.95rem">Tren Form <em>(8 GW Terakhir)</em></div>', unsafe_allow_html=True)
    try:
        summary = get_element_summary(pid)
        hist = [h for h in summary.get("history", [])][-8:]
        if hist:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=[h["round"] for h in hist],
                    y=[h["total_points"] for h in hist],
                    mode="lines+markers",
                    name="Poin",
                    line=dict(color="#00ff87", width=3),
                    marker=dict(size=7, color="#00ff87"),
                )
            )
            fig.add_trace(
                go.Bar(x=[h["round"] for h in hist], y=[h["minutes"] for h in hist], name="Menit", yaxis="y2", marker_color="#7c3aed", opacity=0.75)
            )
            fig.update_layout(
                xaxis_title="Gameweek",
                yaxis_title="Poin",
                yaxis2=dict(title="Menit", overlaying="y", side="right", showgrid=False),
                height=320,
                paper_bgcolor="#fff",
                plot_bgcolor="#f8f9fb",
                font=dict(color="#1a1a2e", size=11),
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Belum ada riwayat pertandingan untuk musim ini.")
    except Exception:
        st.info("Riwayat pemain tidak tersedia.")
