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


if "squad" not in st.session_state:
    st.session_state["squad"] = [i for i in load_squad() if i in by_id]

# --- Squad selection ---
with st.expander("Pilih Skuad 15 Pemain", expanded=len(st.session_state["squad"]) == 0):
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Muat Tim Tersimpan", use_container_width=True):
            st.session_state["_squad_request"] = "load"
    with c2:
        if st.button("Kosongkan Tim", use_container_width=True):
            st.session_state["_squad_request"] = "clear"

    if "_squad_request" in st.session_state:
        request = st.session_state.pop("_squad_request")
        if request == "load":
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
    bank = 100.0 - total_cost

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

        # --- GW Toggle ---
        gw_mode = st.radio("Tampilan proyeksi", ["Next GW", "Next 3 GWs"], horizontal=True, label_visibility="collapsed")
        show_3gw = gw_mode == "Next 3 GWs"

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

        if multi_suggestions:
            for s in multi_suggestions[:6]:
                w = s["player"]
                best_rep = s["reps"][0]
                hit = hit_calculator(w, best_rep, gw_projs, horizon=3)
                hit_badge = (
                    f"<span class='fdr-badge fdr-2'>HIT ✓ net +{hit['net_after_hit']:.1f}</span>"
                    if hit["worth_hit"]
                    else f"<span class='fdr-badge fdr-5'>HIT ✗ net {hit['net_after_hit']:.1f}</span>"
                )
                swing = fixture_swing_badge(gw_projs, best_rep["id"], horizon=3)
                swing_html = f" <span class='fdr-badge fdr-1'>{swing}</span>" if swing else ""

                st.markdown(
                    f"<div class='info-line'>"
                    f"<span style='color:#dc2626;font-weight:500'>{esc(w['web_name'])}</span> "
                    f"<span style='color:#64748b'>({esc(w['team_short'])}, 3GW {s['player_total']:.1f}) → </span>"
                    f"<span style='color:#16a34a;font-weight:500'>{esc(best_rep['web_name'])}</span> "
                    f"<span style='color:#64748b'>({esc(best_rep['team_short'])}, 3GW {best_rep['proj_total']:.1f}) · </span>"
                    f"<span style='color:#37003c;font-weight:600'>+{s['gain']:.2f} (3GW)</span> "
                    f"<span style='color:#64748b'>· GW ini +{s['gain_1gw']:.2f} · {hit_badge}{swing_html}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("Tidak ada transfer yang menguntungkan berdasarkan proyeksi 3 GW ke depan.")

        # --- Rencana 3 GW ---
        st.divider()
        st.markdown('<div class="section" style="font-size:.95rem">Rencana <em>3 Gameweek</em> ke Depan</div>', unsafe_allow_html=True)
        from fpl.horizon import risky_players, squad_plan

        plans = squad_plan(squad, gw_projs, 3)
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
