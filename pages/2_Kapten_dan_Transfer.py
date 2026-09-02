import streamlit as st

from fpl.optimizer import overpriced_players, projection_explanation, risk_players, value_picks
from fpl.ui import apply_theme, autorefresh, esc, fdr_badge_html, load_data, player_card_html, pos_badge_html
from fpl.utils import fmt_price

st.set_page_config(page_title="Kapten & Transfer", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()

from fpl.paststats import attach, load as load_past

with st.spinner("Memuat statistik musim lalu..."):
    dfp = attach(df, load_past(gd))

st.markdown('<div class="section">Kapten & <em>Transfer</em></div>', unsafe_allow_html=True)
st.caption("Rekomendasi kapten, value picks, dan pemain berisiko untuk Gameweek ini.")

players = df.to_dict("records")
available = [p for p in players if p["proj"] and p["proj"] > 0]

st.markdown('<div class="section" style="margin-top:16px">Kandidat <em>Kapten</em> Terbaik</div>', unsafe_allow_html=True)
top5 = sorted(available, key=lambda p: p["proj"], reverse=True)[:5]
tags = ["KAPTEN", "WAKIL", "ALT", "ALT", "ALT"]
cols = st.columns(5)
for col, p, tag in zip(cols, top5, tags):
    with col:
        st.markdown(player_card_html(p, tag=tag), unsafe_allow_html=True)

# --- Simulasi Monte Carlo: Kapten & Wakil (EV + risiko blank) ---
st.markdown('<div class="section">🎲 Kapten <em>Monte Carlo</em> — EV & Risiko Blank</div>', unsafe_allow_html=True)
st.caption(
    "Simulasi ribuan skenario Gameweek (Poisson gol dari kekuatan tim aktual musim ini, "
    "alokasi gol/assist via share xG, CS, menit main, bonus) untuk memilih kapten & wakil "
    "dengan **expected value (EV) tertinggi** — bukan sekadar proyeksi tertinggi."
)
try:
    from fpl.simulator import captain_analysis, load_saved_squad, reference_xi

    squad_rows, xi_ids, src_label = load_saved_squad(df)
    if squad_rows is None:
        with st.spinner("Belum ada skuad tersimpan — memakai XI referensi (greedy terbaik)..."):
            squad_rows = reference_xi(df)
            xi_ids = None
        src_line = "XI referensi dari seluruh pool (simpan skuad di Team Builder untuk hasil sesuai tim Anda)."
    else:
        src_line = f"Skuad: {src_label}"
    with st.spinner("Menjalankan simulasi Monte Carlo..."):
        mc = captain_analysis(gd, df, squad_rows, xi_ids=xi_ids, n=600, seed=7)
    top_mc = mc["top"]
    st.caption(f"{src_line} · {mc['n']} skenario · seed {mc['seed']} (reproducible).")

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("EV Kapten Terbaik (×2)", f"{top_mc['ev_captain']:.1f} pts",
                  help="Ekspektasi poin kapten = 2× poin bila main, 2× wakil bila kapten blank.")
    with m2:
        st.metric("EV XI tanpa kapten", f"{mc['xi_ev']:.1f} pts",
                  help="Total proyeksi 11 starter dari simulasi (belum termasuk bonus kapten).")
    with m3:
        st.metric("Rentang poin kapten p10–p90", f"{mc['cap_distribution']['p10']} – {mc['cap_distribution']['p90']}",
                  help="Distribusi skenario: 10% kapten di bawah p10, 10% di atas p90.")
    with m4:
        st.metric("Risiko blank kapten terbaik", f"{top_mc['p_blank'] * 100:.0f}%",
                  help="Peluang kapten terpilih tidak dimainkan — alasan memilih wakil yang aman.")

    html = '<div class="fpl-card" style="margin-top:8px">'
    for i, c in enumerate(mc["candidates"][:6], 1):
        tag = "KAPTEN MC" if i == 1 else ("WAKIL MC" if i == 2 else f"ALT {i - 1}")
        color = "#37003c" if i == 1 else "#0f172a"
        vc_txt = c["best_vc_name"] or "-"
        html += (
            f'<div class="info-line" style="justify-content:space-between">'
            f'<span><b style="color:{color}">{tag}</b> — {esc(c["web_name"])} '
            f'<span style="color:#64748b">({esc(c["team_short"])})</span></span>'
            f'<span>EV <b style="color:#37003c">{c["ev_captain"]:.2f}</b> · main '
            f'{c["p_plays"] * 100:.0f}% · wakil terbaik <b>{esc(vc_txt)}</b> · '
            f'proyeksi {c["proj"]:.2f}</span></div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
    st.caption(
        "Kunci: wakil kapten (VC) otomatis naik saat kapten blank. VC terbaik = pemain berpeluang "
        "main hampir pasti dengan EV tinggi — seringkali bukan pemain terbaik ke-2."
    )
except Exception as _exc:
    st.warning(f"Simulasi Monte Carlo tidak dapat dijalankan: {_exc}")

st.markdown('<div class="section" style="font-size:.92rem">Detail <em>perhitungan</em></div>', unsafe_allow_html=True)
for p in top5[:3]:
    with st.expander(f"{p['web_name']} ({p['team_short']}) - proyeksi {p['proj']:.2f} poin"):
        st.code(projection_explanation(p))

# --- Fixture Ticker (NEW) ---
st.markdown('<div class="section">Fixture <em>Ticker</em> — FDR 6 Gameweek ke Depan</div>', unsafe_allow_html=True)
st.caption("Jadwal lawan 6 GW ke depan per tim, diurutkan dari run paling mudah. Gunakan untuk transfer jangka panjang.")

from fpl.transfer import fixture_ticker_table

ticker_rows, cur_gw = fixture_ticker_table(gd, n_gws=6)
from fpl.ui import FDR_CELL

ticker_html = '<div class="fpl-card" style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:.8rem">'
# Header
ticker_html += '<tr style="border-bottom:1px solid #e2e8f0;background:#f8fafc">'
ticker_html += '<th style="text-align:left;padding:8px 10px;color:#475569;font-weight:500">Tim</th>'
for i in range(6):
    ticker_html += f'<th style="text-align:center;padding:8px 6px;color:#475569;font-weight:500">GW {cur_gw + i}</th>'
ticker_html += f'<th style="text-align:center;padding:8px 6px;color:#475569;font-weight:500">Avg</th>'
ticker_html += '</tr>'

for row in ticker_rows:
    ticker_html += '<tr style="border-bottom:1px solid #f1f5f9">'
    ticker_html += f'<td style="padding:6px 10px;font-weight:500;color:#0f172a">{esc(row["team_short"])}</td>'
    for i in range(6):
        gw = cur_gw + i
        cell = row.get(f"gw_{gw}", {"text": "-", "fdr": None})
        fdr = cell.get("fdr")
        bg, text_color = FDR_CELL.get(fdr, ("#f8fafc", "#475569"))
        dgw_mark = " ⚡" if cell.get("dgw") else ""
        ticker_html += f'<td style="text-align:center;padding:5px 4px;background:{bg};color:{text_color};font-weight:500;font-size:.7rem">{esc(cell["text"])}{dgw_mark}</td>'
    # Average FDR
    avg = row.get("avg_fdr", 3.0)
    avg_color = "#15803d" if avg <= 2.5 else "#d97706" if avg <= 3.5 else "#b91c1c"
    ticker_html += f'<td style="text-align:center;padding:5px;color:{avg_color};font-weight:600">{avg:.1f}</td>'
    ticker_html += '</tr>'

ticker_html += '</table></div>'
st.markdown(ticker_html, unsafe_allow_html=True)
st.caption("⚡ = Double Gameweek. Tim di atas memiliki jadwal lawan paling ringan.")

st.markdown('<div class="section">Value <em>Picks</em> — Poin Proyeksi per £1 Juta</div>', unsafe_allow_html=True)
st.caption("Pemain murah dengan efisiensi proyeksi poin tertinggi terhadap budget.")
vps = value_picks(available, n=40)
for pos in ("GK", "DEF", "MID", "FWD"):
    subset = [p for p in vps if p["pos"] == pos][:5]
    if not subset:
        continue
    with st.expander(f"{pos} — 5 value picks terbaik", expanded=(pos in ("MID", "FWD"))):
        for p in subset:
            st.markdown(
                f"<div class='info-line'>"
                f"<span style='color:#0f172a;font-weight:500'>{esc(p['web_name'])}</span> "
                f"<span style='color:#64748b'>({esc(p['team_short'])}) · {fmt_price(p['price'])} · "
                f"proyeksi <span style='color:#37003c;font-weight:600'>{p['proj']:.2f}</span> · "
                f"value <span style='color:#d97706;font-weight:500'>{p['value']:.2f}</span> pts/£1jt</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

# --- Differential Picks (NEW) ---
st.markdown('<div class="section">Differential <em>Picks</em> — Kepemilikan Rendah, Proyeksi Tinggi</div>', unsafe_allow_html=True)
st.caption("Pemain dengan kepemilikan komunitas < 5% namun memiliki potensi poin tinggi.")

from fpl.transfer import differential_picks

diffs = differential_picks(available, ownership_threshold=5.0, min_proj=2.0, n=10)
if diffs:
    diff_cols = st.columns(5)
    for col, p in zip(diff_cols, diffs[:5]):
        with col:
            st.markdown(
                f'<div class="p-card">'
                f'<div class="tag alt">DIFF {p["selected_by"]:.1f}%</div>'
                f'<div class="p-name">{esc(p["web_name"])}</div>'
                f'<div class="p-team">{esc(p["team_short"])} {pos_badge_html(p["pos"])}</div>'
                f'<div class="p-proj">{p["proj"]:.2f}</div>'
                f'<div class="p-sub">{fmt_price(p["price"])} · skor diff {p["diff_score"]:.1f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    if len(diffs) > 5:
        with st.expander(f"+ {len(diffs) - 5} differential lainnya"):
            for p in diffs[5:]:
                st.markdown(
                    f"<div class='info-line'>"
                    f"<span style='color:#0f172a;font-weight:500'>{esc(p['web_name'])}</span> "
                    f"<span style='color:#64748b'>({esc(p['team_short'])}, {p['pos']}) · "
                    f"{fmt_price(p['price'])} · proyeksi <span style='color:#37003c;font-weight:600'>{p['proj']:.2f}</span> · "
                    f"ownership <span style='color:#d97706;font-weight:500'>{p['selected_by']:.1f}%</span></span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
else:
    st.info("Tidak ada differential pick yang memenuhi kriteria saat ini.")

st.markdown('<div class="section">Pemain <em>Berisiko</em></div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    st.markdown('<div class="fpl-card"><h3>Cedera / Peluang Main Rendah</h3><div class="card-sub">Banyak dimiliki manajer lain — waspadai potensi rotasi/absen.</div>', unsafe_allow_html=True)
    risky = risk_players(players)
    if risky:
        for p in risky[:8]:
            chance = p.get("chance")
            peluang = f"{float(chance):.0f}%" if chance is not None else "?"
            st.markdown(
                f"<div class='info-line'><span style='color:#dc2626;font-weight:500'>{esc(p['web_name'])}</span> "
                f"<span style='color:#64748b'>({esc(p['team_short'])}) · {p['selected_by']:.1f}% kepemilikan · peluang {peluang}</span></div>",
                unsafe_allow_html=True,
            )
            if p["news"]:
                st.caption(p["news"])
    else:
        st.info("Tidak ada pemain berisiko terdeteksi.")
    st.markdown("</div>", unsafe_allow_html=True)
with c2:
    st.markdown('<div class="fpl-card"><h3>Mahal tapi Proyeksi Rendah</h3><div class="card-sub">Harga premium namun ekspektasi poin GW ini terbatas.</div>', unsafe_allow_html=True)
    over = overpriced_players(players)
    if over:
        for p in over[:8]:
            st.markdown(
                f"<div class='info-line'><span style='color:#d97706;font-weight:500'>{esc(p['web_name'])}</span> "
                f"<span style='color:#64748b'>({esc(p['team_short'])}) · {fmt_price(p['price'])} · proyeksi {p['proj']:.2f}</span></div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("Tidak ada pemain yang mencolok.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="section">Acuan <em>Musim Lalu</em> (2025/26)</div>', unsafe_allow_html=True)
st.caption("Pemain dengan poin tertinggi musim lalu sebagai acuan — dipasangkan dengan proyeksi GW ini dan harga sekarang.")
with st.expander("Top 10 poin musim lalu + proyeksi sekarang", expanded=True):
    stars = dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0)].nlargest(10, "last_points")
    for p in stars.to_dict("records"):
        double = " · <b style='color:#00ff87'>DOUBLE SIGNAL</b>" if p["proj"] and p["proj"] >= 2.2 else ""
        st.markdown(
            f"<div class='info-line'><b style='color:#f59e0b'>{int(p['last_points'])} pts</b> — "
            f"<b style='color:#1a1a2e'>{esc(p['web_name'])}</b> ({esc(p['team_short'])}, {p['pos']}, {fmt_price(p['price'])}) · "
            f"ppg lalu {p['last_ppg']:.2f} · proyeksi GW ini <b style='color:#37003c'>{p['proj']:.2f}</b>{double}</div>",
            unsafe_allow_html=True,
        )
with st.expander("Value musim lalu (poin per £1 juta, harga ≤ £11.0m)"):
    vals = dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0) & (dfp["price"] <= 110)].nlargest(8, "last_value")
    for p in vals.to_dict("records"):
        st.markdown(
            f"<div class='info-line'><b style='color:#00ff87'>{p['last_value']:.2f}</b> pts/£1jt — "
            f"<b style='color:#1a1a2e'>{esc(p['web_name'])}</b> ({esc(p['team_short'])}, {p['pos']}, {fmt_price(p['price'])}) · "
            f"{int(p['last_points'])} pts musim lalu · proyeksi GW ini <b style='color:#37003c'>{p['proj']:.2f}</b></div>",
            unsafe_allow_html=True,
        )

st.divider()
st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem'>"
    "Statistik musim lalu hanya acuan — musim baru bisa berubah (tim baru, taktik, umur). "
    "Gabungkan dengan proyeksi GW ini untuk keputusan terbaik.</p>",
    unsafe_allow_html=True,
)
