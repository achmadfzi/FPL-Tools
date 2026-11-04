"""Rencana detail Gameweek — tabbed, action-first detail page."""

import time

import pandas as pd
import streamlit as st

from fpl.action_plan import (
    build_action_plan,
    confidence_for_captain,
    confidence_for_transfer,
    first_transfer,
)
from fpl.availability import availability
from fpl.ui import apply_theme, autorefresh, countdown_html, load_data
from fpl.ui_simple import (
    action_card,
    confidence_badge,
    is_beginner,
    simple_hero,
    simple_note,
    status_pill,
)
from fpl.utils import fmt_deadline_wib, fmt_price

st.set_page_config(page_title="Rencana Detail · FPL Dashboard", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event
gw_id = int(ev["id"])


@st.cache_data(ttl=600, show_spinner=False)
def compute_payload(gw_key, n_sim=400, horizon=6):
    gd_local, df_local = load_data()
    return build_action_plan(gd_local, df_local, int(gw_key), n_sim=n_sim, horizon=horizon)


simple_hero(
    f"Rencana Detail · GW {gw_id}",
    "Semua keputusan dan angka pendukungnya. Mulai dari tab Ringkasan, lalu buka tab lain jika perlu.",
    kicker="Detail · Bukan Wajib Dibaca Semua",
)
st.markdown(countdown_html(ev.get("deadline_time")), unsafe_allow_html=True)

c1, c2, c3 = st.columns([1, 1, 4])
with c1:
    if st.button("🔄 Hitung ulang", use_container_width=True):
        compute_payload.clear()
        st.rerun()
with c2:
    st.caption("← Kembali ke Minggu Ini lewat sidebar")
with c3:
    st.caption("Perhitungan berat di-cache 10 menit.")

with st.expander("⚙️ Data menit & aksi per pemain — backfill"):
    st.caption("Jalankan sekali agar estimasi menit dan DefCon lebih tajam. Cache sampai GW berikutnya.")
    if st.button("📥 Mulai backfill", key="btn_backfill_hist"):
        from fpl import defcon as _defcon
        from fpl import player_history as _ph

        bar = st.progress(0.0, text="Menghubungi API FPL...")

        def _cb(i, total, name):
            bar.progress(min(1.0, i / max(total, 1)), text=f"Riwayat pemain {i}/{total}: {name}")

        with st.spinner("Mengambil riwayat per-GW..."):
            result = _ph.backfill_if_stale(gd, min_minutes=180, progress=_cb)
            _defcon.build(gd, force=True)
        bar.empty()
        st.success(f"Selesai — {result['fetched']} baru, {result['skipped']} segar, {result['failed']} gagal.")
        st.cache_data.clear()
        st.rerun()

with st.spinner("Menghitung rencana..."):
    payload = compute_payload(gw_id)

state = payload["state"]
line = payload["line"]
plan = payload["plan"]
chips = payload["chips"]
chip_calendar = payload.get("chip_calendar")
cap = line.get("captain") or {}
vc = line.get("vice") or {}

st.caption(
    f"Sumber: **{payload['source']}** · FT: {state.get('ft_detail', '-')} · "
    f"Bank £{float(state.get('bank_value') or 0):.1f}m"
)

tabs = st.tabs(["Ringkasan", "XI & Bench", "Transfer", "Chip", "Peringatan"])

# ---------------------------------------------------------------------------
# Tab 1 — Ringkasan
# ---------------------------------------------------------------------------
with tabs[0]:
    st.markdown("### Keputusan utama")
    st.caption("Empat kartu ini cukup untuk mengambil keputusan. Detail ada di tab sebelah.")

    first = first_transfer(plan)
    if first and int(first.get("gw") or 0) == gw_id:
        tr = first["transfers"][0]
        transfer_headline = f"Jual {tr.get('out_name')} → beli {tr.get('in_name')}"
        transfer_metric = f"{len(first['transfers'])} transfer"
        transfer_meaning = (
            f"Gain {plan.get('gain', 0):+.1f} poin / {plan.get('horizon', 6)} GW. "
            + (f"Penalti -{first.get('hits', 0)}." if first.get("hits") else "Tanpa penalti.")
        )
        transfer_tone = "warn" if first.get("hits") else "good"
    else:
        transfer_headline = "Tidak perlu transfer"
        transfer_metric = f"{state.get('free_transfers', 1)} FT"
        transfer_meaning = "Tidak ada gain yang cukup aman. Menunggu lebih baik."
        transfer_tone = "good"

    chip_gain = 0.0
    chip_label = None
    for key, label, threshold in (("TC", "TC", 4.0), ("BB", "BB", 4.0), ("FH", "FH", 6.0), ("WC", "WC", 8.0)):
        c = (chips or {}).get(key) if isinstance(chips, dict) else None
        if c and float(c.get("gain") or 0) >= threshold and float(c.get("gain") or 0) > chip_gain:
            chip_gain = float(c.get("gain") or 0)
            chip_label = label
    if chip_label:
        chip_headline = f"Pertimbangkan {chip_label}"
        chip_metric = f"+{chip_gain:.1f} poin"
        chip_meaning = "Gain di atas ambang aman. Cek tab Chip sebelum memakai."
        chip_tone = "warn"
        chip_conf = "Sedang"
    else:
        chip_headline = "Simpan chip"
        chip_metric = "Tidak ada chip mendesak"
        chip_meaning = "Belum ada Double/Blank Gameweek yang jelas."
        chip_tone = "good"
        chip_conf = "Tinggi"

    alerts = []
    for r in state.get("squad_rows") or []:
        av = availability(r)
        if av["is_out"] or av["pct"] < 100:
            alerts.append((r.get("web_name"), av))
    if alerts:
        n, av = alerts[0]
        alert_headline = f"{n} — {av['label']}"
        alert_metric = f"{len(alerts)} pemain"
        alert_meaning = av.get("news") or "Peluang main di bawah 100%."
        alert_tone = "bad" if av["is_out"] else "warn"
    else:
        alert_headline = "Skuad aman"
        alert_metric = "0 pemain berisiko"
        alert_meaning = "Semua pemain tersedia penuh."
        alert_tone = "good"

    cols = st.columns(4)
    with cols[0]:
        action_card(
            "🎯 KAPTEN", cap.get("web_name") or "-",
            f"{float(cap.get('ev_captain') or 0):.1f}", "perkiraan poin",
            f"Proyeksi {float(cap.get('proj') or 0):.1f} · main {float(cap.get('p_play') or 0) * 100:.0f}% · wakil {vc.get('web_name') or '-'}",
            confidence_for_captain(line), "good", "Kapten ×2 poin.",
        )
    with cols[1]:
        action_card(
            "🔄 TRANSFER", transfer_headline, transfer_metric, None,
            transfer_meaning, confidence_for_transfer(plan, state), transfer_tone,
            f"Bank £{float(plan.get('final_bank') or 0):.1f}m",
        )
    with cols[2]:
        action_card(
            "🧩 CHIP", chip_headline, chip_metric, None,
            chip_meaning, chip_conf, chip_tone, "Satu chip per GW.",
        )
    with cols[3]:
        action_card(
            "⚠️ PERINGATAN", alert_headline, alert_metric, None,
            alert_meaning, "Rendah" if alerts else "Tinggi", alert_tone,
            "Cek berita resmi sebelum deadline.",
        )

    st.markdown("### Yang perlu dilakukan")
    st.markdown(
        """
        1. Pasang kapten dan wakil.
        2. Cek berita cedera terakhir.
        3. Pastikan bench order.
        4. Kalau tidak yakin, simpan FT.
        """
    )

# ---------------------------------------------------------------------------
# Tab 2 — XI & Bench
# ---------------------------------------------------------------------------
with tabs[1]:
    st.markdown("### Starting XI & Bench")
    st.caption("Kapten (C), wakil (V). Bench 1–3 masuk sesuai urutan jika starter tidak bermain.")

    xi_rows = []
    for p in line.get("xi", []):
        row = {
            "": "C" if p.get("id") == cap.get("id") else ("V" if p.get("id") == vc.get("id") else ""),
            "Pemain": p.get("web_name"),
            "Tim": p.get("team_short"),
            "Posisi": p.get("pos"),
            "Peluang main": f"{float(p.get('p_play') or 0) * 100:.0f}%",
        }
        if not is_beginner():
            row["EV"] = p.get("ev")
            row["Proyeksi"] = p.get("proj")
        xi_rows.append(row)

    bench_rows = []
    for p in line.get("bench", []):
        row = {
            "Pemain": p.get("web_name"),
            "Tim": p.get("team_short"),
            "Posisi": p.get("pos"),
            "Slot": str(p.get("bench_slot", "")),
            "Peluang main": f"{float(p.get('p_play') or 0) * 100:.0f}%",
        }
        if not is_beginner():
            row["EV"] = p.get("ev")
            row["Proyeksi"] = p.get("proj")
        bench_rows.append(row)

    st.dataframe(pd.DataFrame(xi_rows), use_container_width=True, hide_index=True)
    st.markdown("**Bench**")
    st.dataframe(pd.DataFrame(bench_rows), use_container_width=True, hide_index=True)
    st.caption(f"Formasi: {line.get('formation')}")

    if not is_beginner():
        st.markdown("**Detail EV**")
        st.caption(
            f"EV XI: {line.get('ev', 0):.2f} · EV naif: {line.get('ev_naive', 0):.2f} · "
            f"simulasi {line.get('n', 0)} skenario."
        )

# ---------------------------------------------------------------------------
# Tab 3 — Transfer
# ---------------------------------------------------------------------------
with tabs[2]:
    st.markdown("### Rencana Transfer")
    st.caption(
        f"Horizon {plan.get('horizon', 6)} GW. Total rencana {plan.get('total_planned', 0):.1f} poin, "
        f"tahan {plan.get('hold_total', 0):.1f}, gain {plan.get('gain', 0):+.1f}."
    )
    has_transfer = False
    for step in plan.get("plan", []):
        if step.get("transfers"):
            has_transfer = True
            st.markdown(f"**GW {step['gw']}**" + (f" · hit -{step['hits']}" if step.get("hits") else ""))
            rows = [{
                "Jual": t.get("out_name"),
                "Beli": t.get("in_name"),
                "Harga masuk": fmt_price(t.get("in_price", 0)),
                "Peluang main": f"{t.get('in_chance', 0):.0f}%",
                "Status": t.get("in_status"),
            } for t in step["transfers"]]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if not has_transfer:
        st.success("Tidak ada transfer yang direkomendasikan dalam horizon ini. Simpan FT.")

    if not is_beginner():
        with st.expander("Detail planner"):
            st.write(f"Bank akhir: £{plan.get('final_bank', 0):.1f}m · FT akhir: {plan.get('final_ft', '-')}")
            st.write(f"Beam width: {plan.get('beam_width', '-')} · horizon: {plan.get('horizon', '-')}")
            steps = []
            for step in plan.get("plan", []):
                steps.append({
                    "GW": step.get("gw"),
                    "Jumlah transfer": len(step.get("transfers", [])),
                    "Hit": step.get("hits", 0),
                })
            st.dataframe(pd.DataFrame(steps), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 4 — Chip
# ---------------------------------------------------------------------------
with tabs[3]:
    st.markdown("### Chip")
    chips_status = state.get("chips") or {}
    st.caption(
        f"Tersedia sekarang: **{', '.join(chips_status.get('available_now') or []) or 'tidak ada'}**. "
        "Set pertama hangus di GW19."
    )
    if isinstance(chips, dict) and chips.get("error"):
        st.warning(f"Estimasi chip tidak tersedia: {chips['error']}")
    else:
        cc = st.columns(4)
        for col, key, label in zip(cc, ["TC", "BB", "FH", "WC"], ["Triple Captain", "Bench Boost", "Free Hit", "Wildcard"]):
            with col:
                c = (chips or {}).get(key) if isinstance(chips, dict) else None
                if c:
                    st.metric(label, f"+{c.get('gain', 0):.1f} poin", help=c.get("error", "Estimasi gain vs tidak memakai chip."))
                else:
                    st.metric(label, "sudah dipakai")

    if chip_calendar and chip_calendar.get("calendar"):
        st.markdown("**Kalender chip 12 GW**")
        rows = []
        for c in chip_calendar["calendar"]:
            rows.append({
                "Chip": c["chip"],
                "GW": c["gw"],
                "Skor": c["score"],
                "DGW": ", ".join(gd.teams_by_id[t]["short_name"] for t in c.get("dgw") or []) or "-",
                "BGW": ", ".join(gd.teams_by_id[t]["short_name"] for t in c.get("bgw") or []) or "-",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if not is_beginner() and chip_calendar:
        with st.expander("Tabel peluang chip lengkap"):
            rows = [{
                "GW": r["gw"], "TC": r["tc"], "BB": r["bb"], "FH": r["fh"], "WC": r["wc"],
                "DGW": ", ".join(gd.teams_by_id[t]["short_name"] for t in r["dgw"]) or "-",
                "BGW": ", ".join(gd.teams_by_id[t]["short_name"] for t in r["bgw"]) or "-",
            } for r in chip_calendar.get("by_gw", [])]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 5 — Peringatan
# ---------------------------------------------------------------------------
with tabs[4]:
    st.markdown("### Peringatan Skuad")
    rows = []
    squad_set = set(state.get("squad_ids") or [])
    for r in df.to_dict("records"):
        if int(r["id"]) not in squad_set:
            continue
        av = availability(r)
        if av["status"] == "a" and av["pct"] >= 100:
            continue
        rows.append({
            "Pemain": r.get("web_name"),
            "Status": av["status_label"],
            "Peluang main": f"{av['pct']:.0f}%",
            "Kabar": av.get("news") or "-",
            "Saran": av.get("action"),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Pemain dengan peluang main 0% tidak disarankan masuk rencana transfer.")
    else:
        st.success("Tidak ada pemain cedera/diragukan di skuad.")

st.markdown("---")
simple_note(
    "Butuh penjelasan istilah? Buka <b>Kamus FPL</b> di sidebar. "
    "Angka EV/p10–p90 hanya muncul di Mode Analis."
)
