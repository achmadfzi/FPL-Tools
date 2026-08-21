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
    sort_col = st.selectbox(
        "Urutkan berdasarkan",
        ["proj", "form", "ppg", "xGI_per90", "selected_by", "price", "last_points", "last_value", "last_ppg"],
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
        }[c],
    )
with c2:
    ascending = st.checkbox("Urutkan naik", value=False)

view = view.sort_values(sort_col, ascending=ascending)

show = view[["web_name", "team_short", "pos", "price", "proj", "xGI_per90", "last_points", "last_ppg", "form", "ppg", "selected_by", "opponent_short", "fdr", "chance", "status", "id"]].copy()
show.columns = ["Pemain", "Tim", "Pos", "Harga", "Proyeksi", "xGI/90", "Poin Lalu", "PPG Lalu", "Form", "PPG", "Kepemilikan", "Lawan", "FDR", "Peluang", "Status", "id"]

pos_colors = {"GK": "#ca8a04", "DEF": "#2563eb", "MID": "#16a34a", "FWD": "#dc2626"}
fdr_colors = {1: "#16a34a", 2: "#4ade80", 3: "#52525b", 4: "#f59e0b", 5: "#dc2626"}


def style_pos(v):
    return f"background-color:{pos_colors.get(v, '#52525b')};color:#fff;font-weight:800"


def style_fdr(v):
    return f"background-color:{fdr_colors.get(v, '#52525b')};color:#fff;font-weight:800"


def style_status(v):
    c = "#16a34a" if v == "a" else "#dc2626"
    return f"color:{c};font-weight:700"


styled = (
    show.style.map(style_pos, subset=["Pos"])
    .map(style_fdr, subset=["FDR"])
    .map(style_status, subset=["Status"])
    .map(lambda v: f"color:#f59e0b;font-weight:800", subset=["Poin Lalu"])
    .format(
        {
            "Proyeksi": "{:.2f}",
            "xGI/90": "{:.2f}",
            "Poin Lalu": "{:.0f}",
            "PPG Lalu": "{:.2f}",
            "Form": "{:.2f}",
            "PPG": "{:.2f}",
            "Kepemilikan": "{:.1f}%",
            "Peluang": "{:.0f}%",
        }
    )
)
styled = styled.map(lambda v: f"color:#fff", subset=["Pemain", "Tim", "Proyeksi", "Form", "PPG", "Kepemilikan", "Lawan", "PPG Lalu"])
styled = styled.map(lambda v: f"color:#8b93a7", subset=["Harga"])
styled = styled.hide(axis="index")

st.dataframe(styled, use_container_width=True, height=520)

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
          <img src="{photo_url(row['photo_code'])}" style="width:96px;height:120px;object-fit:contain;background:#0d1117;border-radius:12px">
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
          {bar("Estimasi dasar (form)", row['own'], 5.0, '#7c3aed')}
          {bar("Proyeksi resmi FPL", row['ep_next_fpl'], 5.0, '#3b82f6')}
          {bar("Proyeksi akhir", row['proj'] if row['proj'] else 0, 8.0, '#00ff87')}
          <div class="card-sub" style="margin-top:10px">{fixture_line(row)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    info = [
        f"<div class='info-line'>Kepemilikan: <b>{row['selected_by']:.1f}%</b></div>",
        f"<div class='info-line'>Menit bermain: <b>{row['minutes']}</b> | Starter: <b>{row['starts']}</b></div>",
        f"<div class='info-line'>Poin total: <b>{row['total_points']}</b> | Form: <b>{row['form']:.2f}</b> | PPG: <b>{row['ppg']:.2f}</b></div>",
        f"<div class='info-line'>xGI: <b>{row['xGI']:.2f}</b> | xGI/90: <b style='color:#7c3aed'>{row['xGI_per90']:.2f}</b> | xG: <b>{row['xG']:.2f}</b> | xA: <b>{row['xA']:.2f}</b></div>",
        f"<div class='info-line'>Threat: <b>{row['threat']:.0f}</b> | CS prob: <b style='color:#3b82f6'>{row.get('cs_prob', 0):.1%}</b></div>",
    ]
    if row["last_points"]:
        star = "" if row["last_points"] < 200 else " · <b style='color:#f59e0b'>BINTANG MUSIM LALU</b>"
        info.append(
            f"<div class='info-line'>Musim lalu: <b style='color:#f59e0b'>{int(row['last_points'])} poin</b> "
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
                f"<b style='color:{'#4ade80' if f >= 0.88 else '#f59e0b'}'>{rel_label(m, True, row['selected_by'])}</b>{warn}</div>"
            )
        else:
            from fpl.reliability import factor as rel_factor, label as rel_label

            f = rel_factor(0, False, row["selected_by"])
            trust = f >= 0.95
            info.append(
                f"<div class='info-line'>Musim lalu: <b style='color:{'#4ade80' if trust else '#f59e0b'}'>{rel_label(0, False, row['selected_by'])}</b> "
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
                paper_bgcolor="#161b27",
                plot_bgcolor="#161b27",
                font=dict(color="#e7e9ee", size=11),
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Belum ada riwayat pertandingan untuk musim ini.")
    except Exception:
        st.info("Riwayat pemain tidak tersedia.")
