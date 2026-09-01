import json

import pandas as pd
import streamlit as st

from fpl.api import DATA_DIR
from fpl.horizon import player_gw_projections
from fpl.optimizer import best_xi, suggest_transfers
from fpl.ui import (
    apply_theme,
    autorefresh,
    esc,
    fdr_badge_html,
    load_data,
    photo_url,
    pitch_card_html,
    player_img_html,
    pos_badge_html,
    stat_header_html,
)
from fpl.utils import fmt_price

st.set_page_config(page_title="Team Builder", layout="wide")

SQUAD_FILE = DATA_DIR / "squad.json"
SQUAD_SIZE = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}

apply_theme()
autorefresh()

gd, df = load_data()
ev = gd.next_event

st.markdown('<div class="section">Team <em>Builder</em></div>', unsafe_allow_html=True)

players = df.to_dict("records")
by_id = {p["id"]: p for p in players}


def fmt_option(p):
    proj = f"proyeksi {p['proj']:.1f}" if p["proj"] else "bye/risiko"
    return f"{p['web_name']} | {p['team_short']} | {fmt_price(p['price'])} | {proj}"


pos_options = {pos: {fmt_option(p): p["id"] for p in players if p["pos"] == pos} for pos in SQUAD_SIZE}


def load_squad():
    if SQUAD_FILE.exists():
        try:
            return json.loads(SQUAD_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_squad(ids):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQUAD_FILE.write_text(json.dumps(ids))


def labels_for(pos, ids):
    return [
        fmt_option(by_id[i])
        for i in ids
        if i in by_id and by_id[i]["pos"] == pos and fmt_option(by_id[i]) in pos_options[pos]
    ]


from fpl.team import load_manager, sync_team

mgr = load_manager()

# --- Auto-sync squad from FPL Team ID on first load ---
if "squad" not in st.session_state:
    if mgr and mgr.get("squad_ids"):
        # Auto-load from FPL Team ID (no manual click needed)
        auto_ids = [i for i in mgr["squad_ids"] if i in by_id]
        if len(auto_ids) == 15:
            st.session_state["squad"] = auto_ids
            # Try to re-sync for latest data
            try:
                ok, res, err = sync_team(mgr["team_id"], force=False)
                if ok and isinstance(res, dict) and isinstance(res.get("squad_ids"), list):
                    synced = [i for i in res["squad_ids"] if i in by_id]
                    if len(synced) == 15:
                        st.session_state["squad"] = synced
                        mgr = load_manager()  # Reload updated manager data
            except Exception:
                pass
        else:
            st.session_state["squad"] = [i for i in load_squad() if i in by_id]
    else:
        st.session_state["squad"] = [i for i in load_squad() if i in by_id]

# --- Manager info banner ---
if mgr:
    team_name = mgr.get('team_name', 'FPL Team')
    manager_name = mgr.get('manager_name', '')
    overall_pts = mgr.get('summary_overall_points', 0)
    overall_rank = mgr.get('summary_overall_rank', 0)
    bank_mgr = mgr.get('bank', 0.0)
    gw_synced = mgr.get('gw_synced', '?')
    chips_used = [c.get('name', '?') for c in mgr.get('chips_played', [])]
    chips_txt = ', '.join(chips_used) if chips_used else 'Belum ada'

    st.markdown(
        f"""
        <div class="fpl-card" style="padding:14px 18px;margin-bottom:12px;border-left:4px solid #37003c">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
                <div>
                    <div style="font-weight:700;font-size:1.1rem;color:#0f172a">{esc(team_name)}</div>
                    <div style="color:#64748b;font-size:.82rem">Manager: {esc(manager_name)} · ID: {mgr['team_id']} · Sync GW{gw_synced}</div>
                </div>
                <div style="display:flex;gap:16px;font-size:.82rem">
                    <div><span style="color:#64748b">Total Poin:</span> <span style="font-weight:600;color:#37003c">{overall_pts}</span></div>
                    <div><span style="color:#64748b">Rank:</span> <span style="font-weight:600;color:#0f172a">{overall_rank:,}</span></div>
                    <div><span style="color:#64748b">Bank:</span> <span style="font-weight:600;color:#16a34a">£{bank_mgr:.1f}m</span></div>
                    <div><span style="color:#64748b">Chip:</span> <span style="font-weight:500;color:#d97706">{esc(chips_txt)}</span></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# --- Squad selection ---
with st.expander("Pilih Skuad 15 Pemain", expanded=len(st.session_state["squad"]) == 0):
    if mgr:
        c1, c2, c3 = st.columns([1.5, 1, 1])
        with c1:
            btn_label = f"🔄 Tarik Ulang Skuad FPL ({mgr.get('team_name', 'FPL Team')})"
            if st.button(btn_label, use_container_width=True):
                st.session_state["_squad_request"] = "sync_fpl"
        with c2:
            if st.button("Muat Tim Tersimpan", use_container_width=True):
                st.session_state["_squad_request"] = "load"
        with c3:
            if st.button("Kosongkan Tim", use_container_width=True):
                st.session_state["_squad_request"] = "clear"
    else:
        st.info("Masukkan FPL Team ID Anda di bawah untuk auto-sync skuad.")
        team_id_input = st.text_input("FPL Team ID", placeholder="contoh: 925693")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Sync Tim FPL", use_container_width=True) and team_id_input:
                ok, res, err = sync_team(team_id_input, force=True)
                if ok:
                    st.session_state["_squad_request"] = "sync_fpl"
                    st.rerun()
                else:
                    st.error(err)
        with c2:
            if st.button("Muat Tim Tersimpan", use_container_width=True):
                st.session_state["_squad_request"] = "load"

    if "_squad_request" in st.session_state:
        request = st.session_state.pop("_squad_request")
        if request == "sync_fpl" and mgr:
            ok, res, err = sync_team(mgr["team_id"], force=True)
            if ok and isinstance(res, dict) and isinstance(res.get("squad_ids"), list):
                loaded = [i for i in res["squad_ids"] if i in by_id]
                st.session_state["squad"] = loaded
                for pos in SQUAD_SIZE:
                    st.session_state[f"sel_{pos}"] = labels_for(pos, loaded)
        elif request == "load":
            loaded = [i for i in load_squad() if i in by_id]
            st.session_state["squad"] = loaded
            for pos in SQUAD_SIZE:
                st.session_state[f"sel_{pos}"] = labels_for(pos, loaded)
        else:
            st.session_state["squad"] = []
            for pos in SQUAD_SIZE:
                st.session_state[f"sel_{pos}"] = []
        st.rerun()

    sel_new = []
    cols = st.columns(4)
    for col, (pos, need) in zip(cols, SQUAD_SIZE.items()):
        with col:
            stored_ids = [i for i in st.session_state["squad"] if i in by_id and by_id[i]["pos"] == pos]
            default = labels_for(pos, stored_ids)
            chosen = st.multiselect(
                f"Pilih {need} pemain {pos}",
                list(pos_options[pos].keys()),
                default=default,
                key=f"sel_{pos}",
                placeholder=f"Maks {need} pemain",
            )
            ids = [pos_options[pos][opt] for opt in chosen if opt in pos_options[pos]]
            sel_new += ids
            st.caption(f"{len(ids)}/{need} dipilih")

    total_cost = sum(by_id[i]["price"] for i in sel_new) / 10
    bank = 100.0 - total_cost

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total skuad", f"{len(sel_new)}/15")
    c2.metric("Nilai tim", f"£{total_cost:.1f}m")
    c3.metric("Sisa budget", f"£{bank:.1f}m")
    with c4:
        if st.button("Simpan Tim", disabled=len(sel_new) != 15, use_container_width=True):
            save_squad(sel_new)
            st.session_state["squad"] = sel_new
            st.success("Tim tersimpan.")

# If not in expander, use session state
if "sel_new" not in dir() or not sel_new:
    sel_new = [i for i in st.session_state.get("squad", []) if i in by_id]
    total_cost = sum(by_id[i]["price"] for i in sel_new) / 10
    if mgr and set(sel_new) == set(mgr.get("squad_ids", [])):
        bank = float(mgr.get("bank", 0.0))
    else:
        bank = max(0.0, 100.0 - total_cost)

if len(sel_new) == 15:
    squad = [
        {
            "id": p["id"],
            "web_name": p["web_name"],
            "team_short": p["team_short"],
            "team": p["team"],
            "pos": p["pos"],
            "price": p["price"],
            "proj": p["proj"] if p["proj"] else 0.0,
            "opponent_short": p.get("opponent_short"),
            "is_home": p.get("is_home"),
            "fdr": p.get("fdr"),
            "chance": p.get("chance"),
            "status": p.get("status"),
            "photo_code": p.get("photo_code"),
            "selected_by": p.get("selected_by"),
            # Enhanced model fields for rotation risk
            "minutes_per_start": p.get("minutes_per_start", 0),
            "starts": p.get("starts", 0),
            "form": p.get("form", 0),
            "ppg": p.get("ppg", 0),
            "bonus_per_game": p.get("bonus_per_game", 0),
            "ict_per_game": p.get("ict_per_game", 0),
            "minutes": p.get("minutes", 0),
        }
        for i in sel_new
        if (p := by_id[i])
    ]

    # Reliability adjustment
    from fpl.reliability import factor as rel_factor
    from fpl.reliability import label as rel_label
    from fpl.reliability import load as rel_load

    with st.spinner("Memeriksa riwayat menit bermain..."):
        rel = rel_load(gd, ids=[p["id"] for p in squad])
    for p in squad:
        info = rel.get(str(p["id"]), {})
        p["rel_minutes"] = int(info.get("minutes", 0))
        p["rel_has_history"] = bool(info.get("has_history", False))
        p["rel_factor"] = rel_factor(p["rel_minutes"], p["rel_has_history"], p.get("selected_by") or 0)
        p["rel_label"] = rel_label(p["rel_minutes"], p["rel_has_history"], p.get("selected_by") or 0)
        p["proj_raw"] = p["proj"]
        p["proj"] = round(p["proj"] * p["rel_factor"], 2)

    result = best_xi(squad)

    if result:
        # Compute 3 GW projections
        gw_projs = player_gw_projections(df, gd, 3)

        total_proj = result["total"]
        if result["captain"]:
            total_proj += result["captain"]["proj"]

        # --- Stat Header ---
        st.markdown(stat_header_html(squad, ev, bank, total_proj), unsafe_allow_html=True)

        # Always show 3 GW projections
        show_3gw = True

        # --- Layout: Pitch + Picker ---
        col_pitch, col_picker = st.columns([5.7, 4.3])

        with col_pitch:
            # --- PITCH ---
            pitch_html = '<div class="pitch-v2">'
            for pos in ("GK", "DEF", "MID", "FWD"):
                group = [p for p in result["xi"] if p["pos"] == pos]
                group.sort(key=lambda p: p["proj"], reverse=True)
                pitch_html += '<div class="p-row-v2">'
                for p in group:
                    is_cap = result["captain"] and p["id"] == result["captain"]["id"]
                    is_vice = result["vice"] and p["id"] == result["vice"]["id"]
                    pitch_html += pitch_card_html(
                        p,
                        gw_projs=gw_projs if show_3gw else None,
                        gd=gd if show_3gw else None,
                        is_captain=is_cap,
                        is_vice=is_vice,
                    )
                pitch_html += '</div>'
            pitch_html += '</div>'
            st.markdown(pitch_html, unsafe_allow_html=True)

            # --- BENCH ---
            bench_html = '<div class="bench-v2">'
            for p in result["bench"]:
                img = player_img_html(p, cls="pc-img")
                gw_cells = ""
                if show_3gw:
                    projs = gw_projs.get(p["id"], [0.0, 0.0, 0.0])
                    cur = gd.next_event["id"]
                    cells = []
                    for i, val in enumerate(projs[:3]):
                        gw_id = cur + i
                        fx = gd.fixture_for_team_event(p.get("team"), gw_id) if p.get("team") else None
                        if fx:
                            opp_short = gd.teams_by_id.get(fx["opponent"], {}).get("short_name", "?")
                            ha = "K" if fx["is_home"] else "T"
                            fdr = fx.get("difficulty", 3)
                        else:
                            opp_short = "-"
                            ha = ""
                            fdr = 3
                        from fpl.ui import FDR_CELL
                        bg, fg = FDR_CELL.get(fdr, ("#e2e8f0", "#1e293b"))
                        cells.append(
                            f'<div class="gw-cell" style="background:{bg};color:{fg}">'
                            f'<div class="gv">{val:.1f}</div>'
                            f'<div class="gl">{opp_short}({ha})</div></div>'
                        )
                    gw_cells = f'<div class="gw-cells">{"".join(cells)}</div>'

                bench_html += (
                    f'<div class="bc">'
                    f'<div class="pos-label">{p["pos"]}</div>'
                    f'{img}'
                    f'<div class="pc-name">{esc(p["web_name"])}</div>'
                    f'<div class="pc-team" style="font-size:.5rem">{esc(p.get("team_short", ""))}</div>'
                    f'<div class="pc-price">{fmt_price(p["price"])}</div>'
                    f'{gw_cells}'
                    f'</div>'
                )
            bench_html += '</div>'
            st.markdown(bench_html, unsafe_allow_html=True)

            # Formasi + summary metrics
            c1, c2, c3 = st.columns(3)
            c1.metric(
                f"Formasi {result['formation'][0]}-{result['formation'][1]}-{result['formation'][2]}",
                f"{result['total']:.2f} pts",
                "proyeksi XI"
            )
            c2.metric(
                "Dengan kapten (×2)",
                f"{total_proj:.2f} pts",
                f"{result['captain']['web_name']}" if result["captain"] else "-"
            )
            pool_avg = df["proj"].dropna().mean() * 11
            c3.metric("vs rata-rata pool", f"{result['total'] / pool_avg * 100:.0f}%", f"avg {pool_avg:.1f} pts")

            # --- Rotation Risk for YOUR squad ---
            from fpl.optimizer import rotation_risk
            squad_risks = rotation_risk(squad)
            if squad_risks:
                st.markdown(
                    '<div style="margin-top:8px;padding:10px 14px;background:#fef3c7;border-radius:8px;border:1px solid #f59e0b">' 
                    '<div style="font-weight:600;color:#92400e;font-size:.85rem;margin-bottom:4px">⚠️ Risiko Rotasi di Skuad Anda</div>',
                    unsafe_allow_html=True,
                )
                for r in squad_risks:
                    p = r["player"]
                    sev_icon = "🔴" if r["severity"] == "high" else "🟡"
                    reasons = " · ".join(r["reasons"])
                    in_xi = p["id"] in {x["id"] for x in result["xi"]}
                    xi_tag = " <b>(STARTER)</b>" if in_xi else " (bench)"
                    st.markdown(
                        f'<div style="font-size:.82rem;color:#78350f;padding:2px 0">{sev_icon} <b>{esc(p["web_name"])}</b>{xi_tag} — {reasons}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown('</div>', unsafe_allow_html=True)

        with col_picker:
            # --- PLAYER PICKER / EXPLORER PANEL ---
            st.markdown(
                '<div class="fpl-card" style="padding:16px 18px 12px;margin-bottom:8px">'
                '<h3 style="margin-bottom:2px">Cari & Analisis Pemain</h3>'
                '<div class="card-sub" style="margin-bottom:8px">Bandingkan opsi transfer potensial dengan proyeksi poin multi-GW & info lawan.</div>'
                '</div>',
                unsafe_allow_html=True,
            )

            # Filter Controls
            fc1, fc2 = st.columns([1.3, 1])
            with fc1:
                search = st.text_input("Cari nama / tim", "", key="pick_search", placeholder="Ketik nama atau kode tim...")
            with fc2:
                sort_by = st.selectbox(
                    "Urutkan",
                    ["Proyeksi 3 GW", "Proyeksi GW Ini", "Harga Terendah", "Harga Tertinggi", "Form Terbaik", "Kepemilikan", "Lawan Termudah"],
                    key="pick_sort",
                )

            pos_filter = st.radio("Posisi", ["All", "GK", "DEF", "MID", "FWD"], horizontal=True, key="pick_pos")

            # Filter players pool
            squad_ids = {p["id"] for p in squad}
            pool = [p for p in players if p["id"] not in squad_ids and p.get("proj") is not None]

            if pos_filter != "All":
                pool = [p for p in pool if p["pos"] == pos_filter]

            if search:
                s_lower = search.lower()
                pool = [p for p in pool if s_lower in p["web_name"].lower() or s_lower in p["team_short"].lower()]

            cur = gd.next_event["id"]
            rows = []
            for p in pool:
                projs_3 = gw_projs.get(p["id"], [0.0, 0.0, 0.0])
                total_3 = sum(projs_3[:3])
                home = "K" if p.get("is_home") else "T"
                opp = f"{p.get('opponent_short', '-')}({home})" if p.get("opponent_short") else "-"
                
                rows.append({
                    "Pemain": p["web_name"],
                    "Tim": p["team_short"],
                    "Pos": p["pos"],
                    "Harga": p["price"] / 10,
                    "Lawan": opp,
                    "FDR": p.get("fdr") if p.get("fdr") is not None else 3,
                    f"GW {cur}": p.get("proj", 0.0),
                    "3 GW": total_3,
                    "Form": float(p.get("form", 0.0) or 0.0),
                    "Milik": float(p.get("selected_by", 0.0) or 0.0),
                })

            if rows:
                pick_df = pd.DataFrame(rows)

                # Sorting logic
                if sort_by == "Proyeksi 3 GW":
                    pick_df = pick_df.sort_values("3 GW", ascending=False)
                elif sort_by == "Proyeksi GW Ini":
                    pick_df = pick_df.sort_values(f"GW {cur}", ascending=False)
                elif sort_by == "Harga Terendah":
                    pick_df = pick_df.sort_values("Harga", ascending=True)
                elif sort_by == "Harga Tertinggi":
                    pick_df = pick_df.sort_values("Harga", ascending=False)
                elif sort_by == "Form Terbaik":
                    pick_df = pick_df.sort_values("Form", ascending=False)
                elif sort_by == "Kepemilikan":
                    pick_df = pick_df.sort_values("Milik", ascending=False)
                elif sort_by == "Lawan Termudah":
                    pick_df = pick_df.sort_values(["FDR", "3 GW"], ascending=[True, False])

                def style_pos_picker(v):
                    colors = {
                        "GK": "background-color:#d97706;color:#ffffff;font-weight:600;text-align:center",
                        "DEF": "background-color:#2563eb;color:#ffffff;font-weight:600;text-align:center",
                        "MID": "background-color:#16a34a;color:#ffffff;font-weight:600;text-align:center",
                        "FWD": "background-color:#dc2626;color:#ffffff;font-weight:600;text-align:center",
                    }
                    return colors.get(v, "color:#0f172a;text-align:center")

                def style_fdr_picker(v):
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

                def fmt_fdr_picker(v):
                    try:
                        return f"{int(float(v))}"
                    except (ValueError, TypeError):
                        return "-"

                styled_pick = (
                    pick_df.style
                    .map(lambda v: "color:#0f172a;font-weight:500", subset=["Pemain"])
                    .map(lambda v: "color:#475569;font-weight:400;text-align:center", subset=["Tim", "Lawan"])
                    .map(lambda v: "color:#64748b;font-weight:400", subset=["Harga"])
                    .map(style_pos_picker, subset=["Pos"])
                    .map(style_fdr_picker, subset=["FDR"])
                    .map(lambda v: "color:#37003c;font-weight:600", subset=[f"GW {cur}", "3 GW"])
                    .map(lambda v: "color:#0f172a;font-weight:400", subset=["Form", "Milik"])
                    .format(
                        {
                            "Harga": "£{:.1f}m",
                            f"GW {cur}": "{:.2f}",
                            "3 GW": "{:.2f}",
                            "Form": "{:.1f}",
                            "Milik": "{:.1f}%",
                            "FDR": fmt_fdr_picker,
                        }
                    )
                    .hide(axis="index")
                )

                st.dataframe(styled_pick, use_container_width=True, height=480, hide_index=True)
                st.caption(f"Menampilkan {len(pick_df)} pemain yang tersedia. Klik header kolom untuk mengurutkan data.")
            else:
                st.info("Tidak ada pemain yang cocok dengan filter pencarian.")

        # --- Transfer Suggestions ---
        st.divider()
        st.markdown('<div class="section" style="font-size:.95rem">Saran <em>Transfer</em> (Multi-GW Intelligence)</div>', unsafe_allow_html=True)
        st.caption("Transfer dinilai berdasarkan total gain 3 GW ke depan. Badge HIT menunjukkan efektivitas penalti transfer.")

        from fpl.transfer import hit_calculator, multi_gw_transfers, fixture_swing_badge

        pool_t = [
            {
                "id": p["id"],
                "web_name": p["web_name"],
                "team_short": p["team_short"],
                "team": p["team"],
                "pos": p["pos"],
                "price": p["price"],
                "proj": p["proj"] if p["proj"] else 0.0,
            }
            for p in players
        ]

        multi_suggestions = multi_gw_transfers(squad, pool_t, gw_projs, bank=int(bank * 10), horizon=3)

        from typing import cast
        if multi_suggestions:
            for s in multi_suggestions[:6]:
                w = cast(dict, s["player"])
                best_rep = cast(dict, s["reps"][0])
                hit = hit_calculator(w, best_rep, gw_projs, horizon=3)
                hit_badge = (
                    f"<span class='fdr-badge fdr-2'>HIT ✓ net +{hit['net_after_hit']:.1f}</span>"
                    if hit["worth_hit"]
                    else f"<span class='fdr-badge fdr-5'>HIT ✗ net {hit['net_after_hit']:.1f}</span>"
                )
                swing = fixture_swing_badge(gw_projs, best_rep["id"], horizon=3)
                swing_html = f" <span class='fdr-badge fdr-1'>{swing}</span>" if swing else ""

                w_name = w['web_name']  # pyrefly: ignore[bad-index]
                w_team = w['team_short']  # pyrefly: ignore[bad-index]

                st.markdown(
                    f"""
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:10px 14px 8px 14px; margin-bottom:8px; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
                        <div style="display:flex; align-items:center; justify-content:space-between;">
                            <div style="flex:1;">
                                <div style="display:flex; align-items:baseline; gap:6px;">
                                    <span style="font-size:0.7rem; color:#ef4444; font-weight:700; text-transform:uppercase;">OUT</span>
                                    <span style="color:#0f172a; font-weight:600; font-size:1rem;">{esc(w_name)}</span>
                                </div>
                                <div style="color:#64748b; font-size:0.85rem; margin-top:2px;">{esc(w_team)} · £{w['price']/10:.1f}m · Proj: <span style="color:#37003c;font-weight:600;">{s['player_total']:.1f}</span></div>
                            </div>
                            <div style="flex:0 0 auto; display:flex; flex-direction:column; align-items:center; padding:0 12px;">
                                <div style="color:#16a34a; font-weight:700; font-size:1rem; background:#dcfce7; padding:2px 8px; border-radius:12px; margin-bottom:2px;">+{s['gain']:.1f} pts</div>
                                <div style="color:#94a3b8; font-size:1.1rem; margin-top:-2px;">➔</div>
                            </div>
                            <div style="flex:1; text-align:right;">
                                <div style="display:flex; align-items:baseline; gap:6px; justify-content:flex-end;">
                                    <span style="color:#0f172a; font-weight:600; font-size:1rem;">{esc(best_rep['web_name'])}</span>
                                    <span style="font-size:0.7rem; color:#22c55e; font-weight:700; text-transform:uppercase;">IN</span>
                                </div>
                                <div style="color:#64748b; font-size:0.85rem; margin-top:2px;">Proj: <span style="color:#37003c;font-weight:600;">{best_rep['proj_total']:.1f}</span> · £{best_rep['price']/10:.1f}m · {esc(best_rep['team_short'])}</div>
                            </div>
                        </div>
                        <div style="display:flex; justify-content:center; gap:6px; margin-top:8px; padding-top:8px; border-top:1px dashed #f1f5f9; transform:scale(0.9);">
                            {hit_badge}{swing_html}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("Tidak ada transfer yang menguntungkan berdasarkan proyeksi 3 GW ke depan.")

        # --- Saran Transfer 1 GW ---
        st.divider()
        st.markdown('<div class="section" style="font-size:.95rem">Saran <em>Transfer</em> (Fokus 1 GW Berikutnya)</div>', unsafe_allow_html=True)
        st.caption("Transfer agresif untuk memaksimalkan poin hanya di gameweek selanjutnya (jangka pendek).")
        
        single_suggestions = multi_gw_transfers(squad, pool_t, gw_projs, bank=int(bank * 10), horizon=1)
        if single_suggestions:
            for s in single_suggestions[:3]:
                w = cast(dict, s["player"])
                best_rep = cast(dict, s["reps"][0])
                w_proj = gw_projs.get(w['id'], [0])[0]
                rep_proj = gw_projs.get(best_rep['id'], [0])[0]
                st.markdown(
                    f"""
                    <div style="display:flex; align-items:center; justify-content:space-between; background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:10px 14px; margin-bottom:8px; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
                        <div style="flex:1;">
                            <div style="display:flex; align-items:baseline; gap:6px;">
                                <span style="font-size:0.7rem; color:#ef4444; font-weight:700; text-transform:uppercase;">OUT</span>
                                <span style="color:#0f172a; font-weight:600; font-size:1rem;">{esc(w['web_name'])}</span>
                            </div>
                            <div style="color:#64748b; font-size:0.85rem; margin-top:2px;">{esc(w['team_short'])} · £{w['price']/10:.1f}m · Proj: <span style="color:#37003c;font-weight:600;">{w_proj:.1f}</span></div>
                        </div>
                        <div style="flex:0 0 auto; display:flex; flex-direction:column; align-items:center; padding:0 8px; width:100px;">
                            <div style="color:#16a34a; font-weight:700; font-size:1rem; background:#dcfce7; padding:2px 8px; border-radius:12px; margin-bottom:2px;">+{s['gain']:.1f} pts</div>
                            <div style="color:#94a3b8; font-size:1.1rem; margin-top:-2px;">➔</div>
                        </div>
                        <div style="flex:1; text-align:right;">
                            <div style="display:flex; align-items:baseline; gap:6px; justify-content:flex-end;">
                                <span style="color:#0f172a; font-weight:600; font-size:1rem;">{esc(best_rep['web_name'])}</span>
                                <span style="font-size:0.7rem; color:#22c55e; font-weight:700; text-transform:uppercase;">IN</span>
                            </div>
                            <div style="color:#64748b; font-size:0.85rem; margin-top:2px;">Proj: <span style="color:#37003c;font-weight:600;">{rep_proj:.1f}</span> · £{best_rep['price']/10:.1f}m · {esc(best_rep['team_short'])}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("Tidak ada transfer yang menguntungkan untuk 1 GW ke depan.")

        # --- AI Transfer Suggestion ---
        st.divider()
        st.markdown('<div class="section" style="font-size:.95rem">Saran <em>Transfer</em> Menurut AI 🤖</div>', unsafe_allow_html=True)
        st.caption("AI merangkum langkah paling esensial untuk tim Anda minggu ini.")
        
        if multi_suggestions:
            top_ai = multi_suggestions[0]
            ai_w = cast(dict, top_ai["player"])
            ai_rep = cast(dict, top_ai["reps"][0])
            ai_gain = top_ai["gain"]
            
            # Hit check using the 3 GW horizon
            ai_hit = hit_calculator(ai_w, ai_rep, gw_projs, horizon=3)
            hit_msg = "Walaupun terkena penalti -4 poin (HIT), transfer ini **tetap direkomendasikan** karena secara matematis masih surplus poin bersih di akhir GW3." if ai_hit["worth_hit"] else "Jika Anda masih memiliki *Free Transfer*, lakukan perpindahan ini. Namun jika harus kena penalti (HIT), lebih baik ditunda."
            
            reasoning = f"**AI Assistant:** Berdasarkan analisis prediktif algoritma kami, melepas **{ai_w['web_name']}** (£{ai_w['price']/10:.1f}m) adalah keputusan terbaik minggu ini (potensi 3 GW hanya {top_ai['player_total']:.1f} poin). "
            reasoning += f"Sebagai gantinya, masukkan **{ai_rep['web_name']}** (£{ai_rep['price']/10:.1f}m) yang sedang dalam momentum bagus dengan jadwal mendukung (proyeksi 3 GW: {top_ai['reps'][0]['proj_total']:.1f} poin). "
            reasoning += f"Langkah ini akan mendongkrak poin tim Anda sebesar **+{ai_gain:.1f} poin**. {hit_msg}"
            
            st.success(reasoning)
        else:
            st.success("**AI Assistant:** Skuad Anda saat ini sudah sangat ideal! Proyeksi poin Anda sangat maksimal sehingga algoritma kami menyarankan untuk **menyimpan Free Transfer (Roll Transfer)** minggu ini agar Anda punya opsi ganda di GW selanjutnya.")

        # --- Rencana 3 GW ---
        st.divider()
        st.markdown('<div class="section" style="font-size:.95rem">Rencana <em>3 Gameweek</em> ke Depan</div>', unsafe_allow_html=True)
        from fpl.horizon import risky_players, squad_plan

        raw_plans = squad_plan(squad, gw_projs, 3)
        plans: list[dict] = [p for p in raw_plans if p is not None]
        cur = gd.next_event["id"]
        total_3gw = sum(p["total"] for p in plans)
        col_plans = st.columns(3)
        for i, (col, plan) in enumerate(zip(col_plans, plans)):
            gw = cur + i
            cap = plan["captain"]["web_name"] if plan["captain"] else "-"
            label = f"GW {gw}" + (" · GW ini" if i == 0 else "")
            col.metric(label, f"{plan['total']:.2f} pts", f"{plan['formation'][0]}-{plan['formation'][1]}-{plan['formation'][2]} | C: {cap}")
        st.caption(f"**Total 3 GW: {total_3gw:.2f} pts dengan 0 transfer.**")

        risky = risky_players(squad, gw_projs, 3)
        if risky:
            st.markdown("<div class='info-line'><b>Perhatian — kandidat transfer:</b></div>", unsafe_allow_html=True)
            for p, fut in risky:
                st.write(f"**{p['web_name']}** ({p['team_short']}) — proyeksi GW2+GW3 hanya {fut:.2f} pts")

    else:
        st.warning("Skuad belum valid. Pastikan 15 pemain dengan 2 GK, 5 DEF, 5 MID, 3 FWD.")
else:
    st.info(f"Pilih {15 - len(sel_new)} pemain lagi untuk mengaktifkan optimasi.")
