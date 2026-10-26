"""Rencana Aksi Gameweek — one page with every decision for the next GW.

Combines the EV-optimal XI (exact auto-sub rules), captain/vice EV, bench
order, the multi-GW transfer plan (FT/hits/selling prices), chip EV (TC/BB/
FH/WC with the two-set calendar) and squad alerts.
"""

import time

import pandas as pd
import streamlit as st

from fpl.availability import availability
from fpl.ui import apply_theme, autorefresh, countdown_html, load_data
from fpl.utils import fmt_deadline_wib, fmt_price

st.set_page_config(page_title="Rencana Aksi", layout="wide")

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event
gw_id = int(ev.get("id"))

STATE_KEY = "rencana_aksi_payload"


def _fallback_state(df):
    """Build a best-effort state when no FPL team is synced."""
    from fpl.simulator import load_saved_squad, reference_xi

    rows, _xi_ids, _src = load_saved_squad(df)
    source = "skuad tersimpan"
    if rows is None:
        rows = reference_xi(df)
        source = "XI referensi (belum ada skuad tersimpan)"
    pos_of = {int(r["id"]): r.get("pos", "MID") for r in rows}
    return {
        "team_id": None,
        "team_name": None,
        "squad_rows": rows,
        "squad_ids": [int(r["id"]) for r in rows],
        "bank": 0,
        "bank_value": 0.0,
        "team_value": None,
        "sell_prices": {int(r["id"]): int(r["price"]) for r in rows},
        "purchase_prices": {},
        "free_transfers": 1,
        "ft_detail": "estimasi default 1 FT (tim FPL belum tersinkron)",
        "chips": {"available_now": [], "next_set": [], "expires_gw": 19, "current_gw": gw_id},
        "gw_synced": None,
        "synced_at": None,
        "_source": source,
    }


@st.cache_data(ttl=600, show_spinner=False)
def compute_payload(gw_id_key, n_sim=400, horizon=4):
    """Heavy computations for the action page (cached 10 minutes)."""
    from fpl import chips_ev, planner
    from fpl.horizon import player_gw_projections
    from fpl.simulator import optimal_lineup, simulate_squad_matrices

    gd, df = load_data()
    state = planner.manager_state(df, current_gw=int(gw_id_key))
    source = "Tim FPL terhubung"
    if state is None:
        state = _fallback_state(df)
        source = state.pop("_source", "skuad tersimpan")
    else:
        state = dict(state)

    squad_rows = state["squad_rows"]
    sim = simulate_squad_matrices(gd, df, squad_rows, n=n_sim, seed=7)
    line = optimal_lineup(gd, df, squad_rows, sim=sim)

    gw_projs = player_gw_projections(df, gd, horizon=max(4, horizon))
    plan = planner.plan_transfers(gd, df, state, gw_projs, horizon=horizon, beam_width=25)

    chips = None
    try:
        chips = chips_ev.evaluate_chips(gd, df, state, gw_projs, horizon=horizon, n=min(n_sim, 300))
    except Exception as exc:  # never break the page
        chips = {"error": str(exc)}

    return {
        "state": state,
        "source": source,
        "line": line,
        "plan": plan,
        "chips": chips,
        "computed_at": time.time(),
    }


st.markdown('<div class="section">🎯 Rencana <em>Aksi</em> Gameweek Ini</div>', unsafe_allow_html=True)
st.caption(
    f"Semua keputusan Gameweek {gw_id} dalam satu tempat: XI optimal (EV + auto-sub), kapten & wakil, "
    "urutan bench, rencana transfer (FT & hit), dan estimasi chip. Deadline: "
    f"**{fmt_deadline_wib(ev.get('deadline_time'), format_type='full')}**."
)
st.markdown(countdown_html(ev.get("deadline_time")), unsafe_allow_html=True)

c1, c2 = st.columns([1, 4])
with c1:
    if st.button("🔄 Hitung ulang", use_container_width=True, help="Bersihkan cache perhitungan dan muat ulang"):
        compute_payload.clear()
        st.rerun()
with c2:
    st.caption("Perhitungan berat (Monte Carlo 400 skenario, planner 4 GW) di-cache 10 menit agar halaman tetap ringan.")

with st.expander("⚙️ Data menit & aksi per pemain (xMins + DefCon) — backfill"):
    st.caption(
        "Simulator memakai menit main ekspektasi dan aksi bertahan per laga dari riwayat element-summary. "
        "Jalankan backfill sekali (≈200 pemain, ±1 menit, cache 6 jam) agar estimasi lebih tajam. "
        "Data diambil dari API publik FPL dengan jeda sopan antar-request."
    )
    if st.button("📥 Mulai backfill", key="btn_backfill_hist"):
        from fpl import defcon as _defcon
        from fpl import player_history as _ph

        bar = st.progress(0.0, text="Menghubungi API FPL...")

        def _cb(i, total, name):
            bar.progress(min(1.0, i / max(total, 1)), text=f"Riwayat pemain {i}/{total}: {name}")

        with st.spinner("Mengambil riwayat per-GW..."):
            result = _ph.backfill(gd, min_minutes=270, limit=220, progress=_cb)
            _defcon.build(gd, force=True)
        bar.empty()
        st.success(
            f"Selesai — {result['fetched']} baru, {result['skipped']} sudah segar, {result['failed']} gagal."
        )
        st.cache_data.clear()
        st.rerun()

with st.spinner("Menghitung rencana aksi (simulasi & planner)..."):
    payload = compute_payload(gw_id)

state = payload["state"]
line = payload["line"]
plan = payload["plan"]
chips = payload["chips"]

# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------
bank_txt = f"£{state['bank'] / 10:.1f}m" if state.get("bank") is not None else "-"
chips_txt = ", ".join(state["chips"].get("available_now") or []) or "tidak ada"
st.markdown(
    f"""
    <div class="stat-bar">
      <div class="stat-item"><div class="sv">{state.get('team_name') or 'Skuad lokal'}</div><div class="sl">Sumber Skuad</div></div>
      <div class="stat-item"><div class="sv">{state['free_transfers']}</div><div class="sl">Free Transfers</div></div>
      <div class="stat-item"><div class="sv">{bank_txt}</div><div class="sl">Bank</div></div>
      <div class="stat-item"><div class="sv">{chips_txt}</div><div class="sl">Chip Tersisa (set ini)</div></div>
      <div class="stat-item"><div class="sv">GW 19</div><div class="sl">Batas Chip Set-1</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(f"Sumber: **{payload['source']}** · FT: {state.get('ft_detail', '-')}")

# ---------------------------------------------------------------------------
# XI optimal + captain
# ---------------------------------------------------------------------------
st.markdown('<div class="section">1️⃣ XI <em>Optimal</em> — EV + Aturan Auto-Sub</div>', unsafe_allow_html=True)
st.caption(
    "XI dipilih dengan **expected value tertinggi setelah auto-sub** (GK↔GK, urutan bench, formasi tetap valid) "
    "— bukan sekadar jumlah proyeksi. Kapten & wakil juga dari EV simulasi."
)

m1, m2, m3, m4 = st.columns(4)
cap = line.get("captain") or {}
with m1:
    st.metric("EV XI (auto-sub)", f"{line['ev']:.1f} pts",
              help=f"Jumlah proyeksi mentah XI ini: {line['ev_naive']:.1f} — EV memperhitungkan risiko tidak bermain & auto-sub.")
with m2:
    st.metric("Kapten (EV)", f"{cap.get('web_name', '-')} — {cap.get('ev_captain', 0):.1f} pts",
              help=f"EV tanpa wakil: {cap.get('ev_no_vc', 0):.1f}. Risiko blank: {float(cap.get('p_blank') or 0) * 100:.0f}%.")
with m3:
    vc = line.get("vice") or {}
    st.metric("Wakil (VC)", vc.get("web_name", "-"),
              help=f"VC dipilih otomatis: pemain dengan EV tertinggi saat kapten blank. {cap.get('vc_name', '')} adalah wakil terbaik untuk kapten ini.")
with m4:
    dist = line.get("captain_distribution") or {}
    st.metric("Rentang kapten p10–p90", f"{dist.get('p10', 0):.0f} – {dist.get('p90', 0):.0f}",
              help="Distribusi poin kapten (2×) selama 400 skenario. EV ≠ kepastian.")

formation = line.get("formation") or (0, 0, 0)
st.caption(f"Formasi terbaik: **{formation[0]}-{formation[1]}-{formation[2]}**")

xi_rows = []
for p in line.get("xi", []):
    xi_rows.append({
        "Posisi": p["pos"],
        "Pemain": p["web_name"],
        "Tim": p.get("team_short"),
        "Proyeksi": p.get("proj"),
        "EV (skenario)": p.get("ev"),
        "Peluang main": f"{(p.get('p_play') or 0) * 100:.0f}%",
        "Peran": "Kapten" if p["id"] == cap.get("id") else ("Wakil" if p["id"] == (vc.get("id") if vc else None) else ""),
    })
st.dataframe(pd.DataFrame(xi_rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Bench order
# ---------------------------------------------------------------------------
st.markdown('<div class="section" style="font-size:1rem">🪑 Urutan <em>Bench</em> (Auto-Sub)</div>', unsafe_allow_html=True)
bench_rows = []
for p in line.get("bench", []):
    slot = p.get("bench_slot")
    label = "GK cadangan (slot 4)" if slot == "GK" else f"Sub ke-{slot}"
    bench_rows.append({
        "Slot": str(slot),
        "Pemain": p["web_name"],
        "Tim": p.get("team_short"),
        "Proyeksi": p.get("proj"),
        "EV (skenario)": p.get("ev"),
        "Peran": label,
    })
st.dataframe(pd.DataFrame(bench_rows), use_container_width=True, hide_index=True)
st.caption(
    "Urutan bench menentukan siapa yang masuk saat starter tidak bermain. GK cadangan selalu slot 4. "
    "EV di sini adalah poin yang diharapkan kontribusinya bila ia dibutuhkan sebagai pengganti."
)

# ---------------------------------------------------------------------------
# Transfer plan
# ---------------------------------------------------------------------------
st.markdown('<div class="section">2️⃣ Rencana <em>Transfer</em> Multi-GW</div>', unsafe_allow_html=True)
st.caption(
    f"Beam search {plan['horizon']} GW ke depan (budget + limit 3 pemain/klub, harga jual realistis, "
    f"FT {state['free_transfers']} saat ini, hit −4 per transfer ekstra). Baseline *tahan* (tanpa transfer): "
    f"**{plan['hold_total']:.1f} poin**."
)

t1, t2, t3 = st.columns(3)
with t1:
    st.metric("Total rencana", f"{plan['total_planned']:.1f} pts")
with t2:
    st.metric("Gain vs tahan", f"{plan['gain']:+.1f} pts", help="Selisih total proyeksi XI 4 GW dengan rencana transfer optimal vs tidak transfer sama sekali.")
with t3:
    st.metric("Bank & FT akhir", f"£{plan['final_bank']:.1f}m · {plan['final_ft']} FT")

for step in plan["plan"]:
    if not step["transfers"]:
        st.markdown(f"**GW {step['gw']}** · tanpa transfer")
        continue
    hits_txt = f" · hit −{step['hits']}" if step["hits"] else " · gratis (pakai FT)"
    st.markdown(f"**GW {step['gw']}**{hits_txt}")
    rows = []
    for t in step["transfers"]:
        rows.append({
            "Keluar": t["out_name"],
            "Status keluar": t.get("out_status", "-"),
            "Peluang keluar": f"{t['out_chance']:.0f}%" if t.get("out_chance") is not None else "-",
            "Harga jual": fmt_price(t["out_price"]),
            "Masuk": t["in_name"],
            "Status masuk": t.get("in_status", "-"),
            "Peluang masuk": f"{t['in_chance']:.0f}%" if t.get("in_chance") is not None else "-",
            "Harga": fmt_price(t["in_price"]),
            "Gain horizon": t.get("gain_horizon"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.caption(
    "Angka gain memakai proyeksi horizon (mean-reverting). Jika transfer GW ini terasa tipis (< +0.5 pts), "
    "pertimbangkan menyimpan FT untuk minggu depan."
)

# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------
st.markdown('<div class="section">3️⃣ <em>Chip</em> — Kapan Pakai?</div>', unsafe_allow_html=True)
chips_status = state["chips"]
st.caption(
    f"Chip set-1 (GW1–19) tersisa: **{', '.join(chips_status.get('available_now') or []) or 'tidak ada'}**. "
    "Satu chip per Gameweek. Chip set-2 (WC/FH/TC/BB) terbuka mulai GW20."
)

if isinstance(chips, dict) and chips.get("error"):
    st.warning(f"Estimasi chip tidak tersedia: {chips['error']}")
else:
    c = st.columns(4)
    tc = chips.get("TC")
    bb = chips.get("BB")
    fh = chips.get("FH")
    wc = chips.get("WC")
    with c[0]:
        if tc:
            st.metric("TC gain (GW ini)", f"+{tc['gain']:.1f} pts",
                      help=f"Triple Captain {tc['captain']} ({tc.get('team_short')}) vs kapten biasa. "
                           f"EV 3×: {tc['ev_triple']}, 2×: {tc['ev_normal']}. Simpan untuk DGW/premium vs lawan mudah.")
        else:
            st.metric("TC", "sudah dipakai", help="Triple Captain tidak tersisa di set chip ini.")
    with c[1]:
        if bb:
            st.metric("BB gain (GW ini)", f"+{bb['gain']:.1f} pts",
                      help=f"EV 15 pemain ({bb['squad15_ev']}) − EV XI auto-sub ({bb['xi_ev_autosub']}). "
                           "Paling kuat saat bench juga starter + DGW.")
        else:
            st.metric("BB", "sudah dipakai")
    with c[2]:
        if fh:
            st.metric("FH gain (GW ini)", f"+{fh['gain']:.1f} pts",
                      help=f"XI terbaik pasar ({fh['best_xi_proj']}) vs XI skuad sekarang ({fh['current_xi_proj']}), "
                           f"budget £{fh['budget']}m. Simpan untuk BGW/blank besar.")
        else:
            st.metric("FH", "sudah dipakai")
    with c[3]:
        if wc:
            st.metric(f"WC gain ({wc['horizon']} GW)", f"+{wc['gain']:.1f} pts",
                      help=f"Skuad optimal {wc['horizon']} GW ({wc['best_total']}) vs skuad sekarang ({wc['current_total']}) "
                           f"dengan budget £{wc['budget']}m (harga jual + bank).")
        else:
            st.metric("WC", "sudah dipakai")

    tc_alt = (chips.get("TC") or {}).get("alternatives") or []
    if tc_alt:
        st.caption("Kandidat TC: " + " · ".join(f"{a['name']} (+{a['extra_ev']:.1f})" for a in tc_alt[:5]))

# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
st.markdown('<div class="section" style="font-size:1rem">⚠️ <em>Peringatan</em> Skuad</div>', unsafe_allow_html=True)
squad_set = set(state["squad_ids"])
recommended_out = {}
for step in plan.get("plan", []):
    for t in step.get("transfers", []):
        key = t.get("out_id") or t.get("out_name")
        recommended_out[key] = f"{t.get('in_name')} (GW {step.get('gw')})"

alerts = []
for r in df.to_dict("records"):
    pid = int(r["id"])
    if pid not in squad_set:
        continue
    name = r.get("web_name")
    av = availability(r)
    if av["status"] == "a" and av["pct"] >= 100:
        continue
    kabar = av["news"] or "-"
    if av["return_text"]:
        kabar = f"{kabar} · kembali: {av['return_text']}"
    alerts.append({
        "Pemain": name,
        "Status": av["status_label"],
        "Peluang GW ini": f"{av['this_pct']:.0f}%",
        "Peluang GW depan": f"{av['next_pct']:.0f}%",
        "Kabar": kabar[:90],
        "Saran transfer": recommended_out.get(pid, recommended_out.get(name, "Belum ada opsi lebih baik")),
    })
if alerts:
    st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
    st.caption("Saran transfer berasal dari rencana multi-GW di atas; pemain masuk dengan peluang 0% sudah difilter.")
else:
    st.success("Tidak ada pemain skuad dengan status diragukan/cedera. Aman!")

bench_hi = [p for p in line.get("bench", []) if (p.get("proj") or 0) >= 5.5]
if bench_hi:
    names = ", ".join(f"{p['web_name']} ({p['proj']:.1f})" for p in bench_hi)
    st.info(f"Bench dengan proyeksi tinggi: **{names}** — cek apakah XI & urutan bench sudah optimal (lihat bagian 1).")

st.markdown(
    "<p style='color:#8b93a7;font-size:.72rem;margin-top:24px'>"
    "EV dihitung dari 400 simulasi Monte Carlo (Poisson gol dari kekuatan tim, alokasi xG/xA, "
    "penalti, kartu, DefCon, CS, menit main, bonus) dan di-cache 10 menit. "
    "Keputusan akhir tetap di tangan Anda — cek kabar tim sebelum deadline.</p>",
    unsafe_allow_html=True,
)
