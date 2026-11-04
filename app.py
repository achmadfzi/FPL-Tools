"""Minggu Ini — satu layar untuk keputusan Gameweek.

The old Beranda was an analytics catalogue.  This page is deliberately
action-first: captain, transfer, chip, and alerts.  Every number has a plain
language meaning; detailed metrics live behind links/expanders.
"""

import pandas as pd
import streamlit as st

from fpl.action_plan import (
    build_action_plan,
    confidence_for_captain,
    confidence_for_transfer,
    first_transfer,
)
from fpl.availability import availability
from fpl.ui import (
    apply_theme,
    autorefresh,
    countdown_html,
    last_updated,
    load_data,
    refresh,
)
from fpl.ui_simple import (
    action_card,
    is_beginner,
    simple_hero,
    simple_note,
    status_pill,
)
from fpl.utils import fmt_deadline_wib, fmt_price

st.set_page_config(page_title="Minggu Ini · FPL Dashboard", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event
gw_id = int(ev["id"])

# Keep the accuracy tracker alive even if the user only opens this page.
try:
    from fpl.accuracy import auto_update_history, save_projections

    save_projections(gw_id, df)
    auto_update_history()
except Exception:
    pass


@st.cache_data(ttl=600, show_spinner=False)
def _action_payload(gw_key, n_sim=400, horizon=6):
    gd_local, df_local = load_data()
    return build_action_plan(gd_local, df_local, int(gw_key), n_sim=n_sim, horizon=horizon)


with st.spinner("Menyiapkan keputusan Gameweek..."):
    payload = _action_payload(gw_id)

state = payload["state"]
line = payload["line"]
plan = payload["plan"]
chips = payload["chips"]
chip_calendar = payload.get("chip_calendar")
cap = line.get("captain") or {}
vc = line.get("vice") or {}
source = payload.get("source", "skuad tersimpan")

simple_hero(
    f"Minggu Ini · GW {gw_id}",
    f"Deadline: {fmt_deadline_wib(ev.get('deadline_time'), format_type='full')}",
)

c_refresh, c_info = st.columns([1, 5])
with c_refresh:
    if st.button("🔄 Segarkan Data", use_container_width=True):
        refresh()
with c_info:
    st.caption(
        f"Data terakhir: {last_updated()} · Sumber skuad: **{source}** · "
        "Semua angka adalah perkiraan, bukan jaminan."
    )
st.markdown(countdown_html(ev.get("deadline_time")), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Four decision cards
# ---------------------------------------------------------------------------
st.markdown('<div class="section">Keputusan <em>Minggu Ini</em></div>', unsafe_allow_html=True)

cap_name = cap.get("web_name") or "-"
cap_team = cap.get("team_short") or ""
cap_ev = float(cap.get("ev_captain") or 0)
cap_proj = float(cap.get("proj") or 0)
cap_play = float(cap.get("p_play") or 0)
cap_conf = confidence_for_captain(line)

first = first_transfer(plan)
if first and int(first.get("gw") or 0) == gw_id:
    tr = first["transfers"][0]
    transfer_headline = f"Jual {tr.get('out_name')} → beli {tr.get('in_name')}"
    transfer_metric = f"{len(first['transfers'])} transfer"
    transfer_meaning = (
        f"Perkiraan gain {plan.get('gain', 0):+.1f} poin dalam {plan.get('horizon', 6)} GW. "
        + (f"Ada penalti -{first.get('hits', 0)} poin." if first.get("hits") else "Tanpa penalti.")
    )
    transfer_tone = "warn" if first.get("hits") else "good"
else:
    transfer_headline = "Tidak perlu transfer minggu ini"
    transfer_metric = f"{state.get('free_transfers', 1)} FT"
    nxt = first_transfer(plan)
    if nxt:
        nt = nxt["transfers"][0]
        transfer_meaning = (
            f"Rencana berikutnya: GW {nxt.get('gw')} — {nt.get('out_name')} → {nt.get('in_name')}. "
            "Menunggu momen yang lebih baik."
        )
    else:
        transfer_meaning = "Tidak ada transfer yang cukup menguntungkan dalam horizon rencana."
    transfer_tone = "good"
transfer_conf = confidence_for_transfer(plan, state)

# Chip: only recommend using it when the estimated gain is clearly meaningful.
chip_bits = []
for key, label, threshold in (("TC", "Triple Captain", 4.0), ("BB", "Bench Boost", 4.0), ("FH", "Free Hit", 6.0), ("WC", "Wildcard", 8.0)):
    c = (chips or {}).get(key) if isinstance(chips, dict) else None
    if c and float(c.get("gain") or 0) >= threshold:
        chip_bits.append((label, float(c.get("gain") or 0)))
if chip_bits:
    label, gain = max(chip_bits, key=lambda x: x[1])
    chip_headline = f"Pertimbangkan {label}"
    chip_metric = f"+{gain:.1f} poin"
    chip_meaning = "Chip ini punya estimasi gain di atas ambang aman. Cek detail sebelum memakai."
    chip_tone = "warn"
    chip_conf = "Sedang"
else:
    chip_headline = "Simpan chip minggu ini"
    chip_metric = "Tidak ada chip mendesak"
    best = (chip_calendar or {}).get("best") or {}
    if best.get("TC"):
        chip_meaning = (
            f"TC terbaik diperkirakan GW {best['TC']['gw']} (+{best['TC']['score']:.1f}). "
            "Chip set pertama hangus di GW19."
        )
    else:
        chip_meaning = "Belum ada Double/Blank Gameweek yang jelas. Simpan chip untuk momen lebih baik."
    chip_tone = "good"
    chip_conf = "Tinggi"

# Alerts from the saved squad.
squad_rows = state.get("squad_rows") or []
alerts = []
for r in squad_rows:
    av = availability(r)
    if av["is_out"] or av["pct"] < 100:
        alerts.append((r.get("web_name"), av))
alerts.sort(key=lambda x: (x[1]["severity"], -(float(x[0] is not None))))
if alerts:
    a_name, a_av = alerts[0]
    alert_headline = f"{a_name} — {a_av['label']}"
    alert_metric = f"{len(alerts)} pemain perlu dicek"
    alert_meaning = a_av.get("news") or "Peluang main di bawah 100%. Pantau berita menjelang deadline."
    alert_tone = "bad" if a_av["is_out"] else "warn"
    alert_conf = "Rendah" if a_av["is_out"] else "Sedang"
else:
    alert_headline = "Skuad aman"
    alert_metric = "Tidak ada cedera baru"
    alert_meaning = "Semua pemain di skuad berstatus tersedia penuh."
    alert_tone = "good"
    alert_conf = "Tinggi"

cols = st.columns(4)
with cols[0]:
    action_card(
        "🎯 KAPTEN", cap_name, f"{cap_ev:.1f}", "perkiraan poin kapten",
        f"Proyeksi {cap_proj:.1f} poin · peluang main {cap_play * 100:.0f}% · wakil: {vc.get('web_name') or '-'}",
        cap_conf, "good" if cap_conf == "Tinggi" else "warn",
        "Kapten mendapat 2× poin.",
    )
with cols[1]:
    action_card(
        "🔄 TRANSFER", transfer_headline, transfer_metric, None,
        transfer_meaning, transfer_conf,
        transfer_tone,
        f"Bank £{float(plan.get('final_bank') or 0):.1f}m · FT akhir {plan.get('final_ft', '-')}",
    )
with cols[2]:
    action_card(
        "🧩 CHIP", chip_headline, chip_metric, None,
        chip_meaning, chip_conf, chip_tone,
        "Satu chip per Gameweek.",
    )
with cols[3]:
    action_card(
        "⚠️ PERINGATAN", alert_headline, alert_metric, None,
        alert_meaning, alert_conf, alert_tone,
        "Cek berita resmi sebelum deadline.",
    )

# ---------------------------------------------------------------------------
# XI & bench — no advanced numbers by default
# ---------------------------------------------------------------------------
st.markdown('<div class="section">Starting <em>XI</em> & Bench</div>', unsafe_allow_html=True)
st.caption(
    "Ini susunan yang direkomendasikan. Kapten ditandai (C), wakil (V). "
    "Urutan bench menentukan siapa yang masuk otomatis jika starter tidak bermain."
)

xi_rows = []
for i, p in enumerate(line.get("xi", []), 1):
    xi_rows.append({
        "": "C" if p.get("id") == cap.get("id") else ("V" if p.get("id") == vc.get("id") else ""),
        "Pemain": p.get("web_name"),
        "Tim": p.get("team_short"),
        "Posisi": p.get("pos"),
        "Peluang main": f"{float(p.get('p_play') or 0) * 100:.0f}%",
    })
bench_rows = []
for p in line.get("bench", []):
    bench_rows.append({
        "Pemain": p.get("web_name"),
        "Tim": p.get("team_short"),
        "Posisi": p.get("pos"),
        "Slot": str(p.get("bench_slot", "")),
        "Peluang main": f"{float(p.get('p_play') or 0) * 100:.0f}%",
    })

c_xi, c_bench = st.columns([3, 2])
with c_xi:
    st.markdown("**Starting XI**")
    st.dataframe(pd.DataFrame(xi_rows), use_container_width=True, hide_index=True, height=430)
with c_bench:
    st.markdown("**Bench**")
    st.dataframe(pd.DataFrame(bench_rows), use_container_width=True, hide_index=True)
    st.caption("GK bench selalu di slot 4. Sub 1–3 masuk sesuai urutan.")

if not is_beginner():
    st.markdown("**Angka detail XI**")
    detail_rows = [{
        "Pemain": p.get("web_name"),
        "EV": p.get("ev"),
        "Proyeksi": p.get("proj"),
        "Peluang main": p.get("p_play"),
    } for p in line.get("xi", [])]
    st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Why + next actions
# ---------------------------------------------------------------------------
st.markdown('<div class="section">Kenapa & <em>Aksi Berikutnya</em></div>', unsafe_allow_html=True)
c_why, c_next = st.columns(2)
with c_why:
    with st.expander("💡 Kenapa kapten ini?", expanded=False):
        st.write(
            f"**{cap_name}** dipilih karena kombinasi proyeksi poin, peluang main, dan potensi bonus. "
            f"Wakil **{vc.get('web_name') or '-'}** otomatis menggantikan jika kapten tidak bermain."
        )
        if not is_beginner():
            st.write(f"EV kapten: {cap_ev:.2f} · proyeksi: {cap_proj:.2f} · peluang main: {cap_play * 100:.0f}%")
    with st.expander("💡 Kenapa transfer ini?", expanded=False):
        if first and int(first.get("gw") or 0) == gw_id:
            st.write(transfer_meaning)
            for t in first.get("transfers", []):
                gain = t.get("gain_horizon")
                gain_txt = f"{float(gain):+.1f}" if gain is not None else "-"
                st.write(f"- {t.get('out_name')} → {t.get('in_name')} (gain {gain_txt})")
        else:
            st.write(transfer_meaning)
            st.write("Menunggu gain yang lebih pasti lebih baik daripada transfer karena panik.")
    with st.expander("💡 Kenapa chip ini?", expanded=False):
        st.write(chip_meaning)
        if not is_beginner() and chip_calendar:
            for c in chip_calendar.get("calendar", []):
                st.write(f"- {c['chip']} → GW {c['gw']} (skor {c['score']:.1f})")
with c_next:
    st.markdown(
        """
        **Checklist sebelum deadline**
        1. Pasang kapten & wakil.
        2. Cek berita cedera terakhir.
        3. Pastikan urutan bench sudah benar.
        4. Kalau tidak yakin, jangan transfer hanya karena panik.
        """
    )
    if alerts:
        st.warning("Pemain yang perlu dicek: " + ", ".join(n for n, _ in alerts[:4]))

# ---------------------------------------------------------------------------
# Links to detail pages
# ---------------------------------------------------------------------------
st.markdown('<div class="section">Kalau Mau <em>Lebih Detail</em></div>', unsafe_allow_html=True)
link_cols = st.columns(3)
with link_cols[0]:
    st.page_link("pages/0_Rencana_Detail.py", label="📋 Rencana detail (XI, transfer, chip)", use_container_width=True)
    st.page_link("pages/2_Kapten_dan_Transfer.py", label="🎯 Bandingkan kandidat kapten", use_container_width=True)
with link_cols[1]:
    st.page_link("pages/3_Skuad_Saya.py", label="👥 Susun / ubah skuad", use_container_width=True)
    st.page_link("pages/1_Cari_Pemain.py", label="🔎 Cari pemain", use_container_width=True)
with link_cols[2]:
    st.page_link("pages/4_Chip_dan_Lab.py", label="🧩 Kalender chip", use_container_width=True)
    st.page_link("pages/5_Performa.py", label="📈 Akurasi & performa model", use_container_width=True)

simple_note(
    "Angka besar adalah <b>perkiraan poin rata-rata</b>, bukan jaminan. "
    "Buka <b>Kamus FPL</b> di sidebar kalau ada istilah yang belum jelas."
)

if not is_beginner():
    st.markdown('<div class="section" style="font-size:.9rem">Detail tambahan (Mode Analis)</div>', unsafe_allow_html=True)
    st.caption(
        f"EV XI: {line.get('ev', 0):.2f} · proyeksi naif: {line.get('ev_naive', 0):.2f} · "
        f"formasi: {line.get('formation')} · simulasi: {line.get('n', 0)} skenario."
    )
