import json

import pandas as pd
import streamlit as st

from fpl.api import DATA_DIR
from fpl.availability import availability
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
    transfer_card_html,
)
from fpl.utils import fmt_price

st.set_page_config(page_title="Team Builder", layout="wide")

SQUAD_FILE = DATA_DIR / "squad.json"
RECOMMENDED_FILE = DATA_DIR / "recommended_squad.json"
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


def load_recommended():
    if RECOMMENDED_FILE.exists():
        try:
            return json.loads(RECOMMENDED_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_squad(ids):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQUAD_FILE.write_text(json.dumps(ids))


def reset_dnd_budget():
    """Forget the drag-and-drop budget when the squad source changes."""
    st.session_state.pop("dnd_budget_tenths", None)
    st.session_state.pop("dnd_budget_team_id", None)


def labels_for(pos, ids):
    return [
        fmt_option(by_id[i])
        for i in ids
        if i in by_id and by_id[i]["pos"] == pos and fmt_option(by_id[i]) in pos_options[pos]
    ]


def selected_ids_from_widgets():
    """Current selection from the multiselect/component-backed keys.

    This is the source of truth when switching between Daftar and Drag & Drop;
    ``st.session_state["squad"]`` is only the persisted/saved snapshot.
    """
    ids = []
    for pos in SQUAD_SIZE:
        chosen = st.session_state.get(f"sel_{pos}", [])
        ids += [pos_options[pos][opt] for opt in chosen if opt in pos_options[pos]]
    return ids


def lineup_gw_cells(player, gw_projs):
    """Three compact fixture/projection cells for the pitch card."""
    cells = []
    cur = int(gd.next_event["id"])
    projs = gw_projs.get(int(player["id"]), [0.0, 0.0, 0.0])
    for offset, val in enumerate(projs[:3]):
        gw_id = cur + offset
        fixture = gd.fixture_for_team_event(player.get("team"), gw_id)
        if fixture:
            opponent = gd.teams_by_id.get(fixture["opponent"], {}).get("short_name", "?")
            home_away = "K" if fixture["is_home"] else "T"
            fdr = fixture.get("difficulty", 3)
        else:
            opponent, home_away, fdr = "-", "", 3
        cells.append({
            "opp": opponent,
            "ha": home_away,
            "fdr": int(fdr or 3),
            "pts": round(float(val or 0), 2),
        })
    return cells


from fpl.team import load_manager, sync_team

mgr = load_manager()

# --- Initialize squad on first page load ---
if "squad" not in st.session_state:
    saved = [i for i in load_squad() if i in by_id]
    if len(saved) == 15:
        # 1. Load user's saved squad from squad.json
        st.session_state["squad"] = saved
    elif mgr and mgr.get("squad_ids"):
        # 2. Fallback to FPL Team ID if no saved squad exists yet
        auto_ids = [i for i in mgr["squad_ids"] if i in by_id]
        st.session_state["squad"] = auto_ids if len(auto_ids) == 15 else saved
    else:
        st.session_state["squad"] = saved

# Ensure multiselect session states are synchronized
for pos in SQUAD_SIZE:
    if f"sel_{pos}" not in st.session_state:
        pos_ids = [i for i in st.session_state.get("squad", []) if i in by_id and by_id[i]["pos"] == pos]
        st.session_state[f"sel_{pos}"] = labels_for(pos, pos_ids)

# --- Manager info banner ---
if mgr:
    team_name = mgr.get("team_name", "FPL Team")
    manager_name = mgr.get("manager_name", "")
    overall_pts = mgr.get("summary_overall_points", 0)
    overall_rank = mgr.get("summary_overall_rank", 0)
    bank_mgr = mgr.get("bank", 0.0)
    gw_synced = mgr.get("gw_synced", "?")
    chips_used = [c.get("name", "?") for c in mgr.get("chips_played", [])]
    chips_txt = ", ".join(chips_used) if chips_used else "Belum ada"

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
with st.expander("Pilih Skuad 15 Pemain", expanded=len(st.session_state.get("squad", [])) == 0):
    if mgr:
        c1, c2, c3, c4 = st.columns([1.2, 1, 1.1, 0.7])
        with c1:
            btn_label = f"🔄 Skuad FPL Asli ({mgr.get('team_name', 'FPL')})"
            if st.button(btn_label, use_container_width=True):
                ok, res, err = sync_team(mgr["team_id"], force=True, update_squad_file=False)
                if ok and isinstance(res, dict) and isinstance(res.get("squad_ids"), list):
                    loaded = [i for i in res["squad_ids"] if i in by_id]
                    st.session_state["squad"] = loaded
                    for pos in SQUAD_SIZE:
                        st.session_state[f"sel_{pos}"] = labels_for(pos, loaded)
                    reset_dnd_budget()
                    st.toast(f"Skuad FPL ({mgr.get('team_name')}) dimuat!", icon="🔄")
                    st.rerun()
        with c2:
            if st.button("📁 Tim Tersimpan", use_container_width=True):
                loaded = [i for i in load_squad() if i in by_id]
                if len(loaded) == 15:
                    st.session_state["squad"] = loaded
                    for pos in SQUAD_SIZE:
                        st.session_state[f"sel_{pos}"] = labels_for(pos, loaded)
                    reset_dnd_budget()
                    st.toast("Tim tersimpan dimuat!", icon="📁")
                    st.rerun()
                else:
                    st.warning("Belum ada data tim tersimpan di squad.json.")
        with c3:
            if st.button("💡 Rekomendasi AI", use_container_width=True):
                rec = [i for i in load_recommended() if i in by_id]
                if len(rec) == 15:
                    st.session_state["squad"] = rec
                    for pos in SQUAD_SIZE:
                        st.session_state[f"sel_{pos}"] = labels_for(pos, rec)
                    reset_dnd_budget()
                    st.toast("Skuad rekomendasi AI dimuat!", icon="💡")
                    st.rerun()
                else:
                    st.info("Jalankan recommend.py untuk menghasilkan rekomendasi AI.")
        with c4:
            if st.button("🗑️ Kosongkan", use_container_width=True):
                st.session_state["squad"] = []
                for pos in SQUAD_SIZE:
                    st.session_state[f"sel_{pos}"] = []
                reset_dnd_budget()
                st.rerun()
    else:
        st.info("Masukkan FPL Team ID Anda di bawah untuk auto-sync skuad.")
        team_id_input = st.text_input("FPL Team ID", placeholder="contoh: 925693")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Sync Tim FPL", use_container_width=True) and team_id_input:
                ok, res, err = sync_team(team_id_input, force=True, update_squad_file=True)
                if ok and isinstance(res, dict) and isinstance(res.get("squad_ids"), list):
                    loaded = [i for i in res["squad_ids"] if i in by_id]
                    st.session_state["squad"] = loaded
                    for pos in SQUAD_SIZE:
                        st.session_state[f"sel_{pos}"] = labels_for(pos, loaded)
                    reset_dnd_budget()
                    st.rerun()
                else:
                    st.error(err)
        with c2:
            if st.button("📁 Tim Tersimpan", use_container_width=True):
                loaded = [i for i in load_squad() if i in by_id]
                if len(loaded) == 15:
                    st.session_state["squad"] = loaded
                    for pos in SQUAD_SIZE:
                        st.session_state[f"sel_{pos}"] = labels_for(pos, loaded)
                    reset_dnd_budget()
                    st.rerun()

    from fpl.squad_builder import (
        compact_player,
        group_player_ids,
        normalize_selected,
        selected_ids,
        validate_selection,
    )

    builder_mode = st.radio(
        "Cara menyusun skuad",
        ["🧲 Drag & Drop", "📋 Daftar"],
        horizontal=True,
        key="squad_builder_mode",
        help="Drag & Drop memakai komponen JavaScript; mode Daftar tetap memakai multiselect lama.",
    )
    dnd_mode = builder_mode.startswith("🧲")
    dnd_budget_tenths = None
    sel_new = []

    if dnd_mode:
        current_ids = selected_ids_from_widgets()
        current_selected = group_player_ids(current_ids, by_id)
        initial_cost = sum(int(by_id[i].get("price") or 0) for i in current_ids)
        stored_budget = st.session_state.get("dnd_budget_tenths")
        stored_team = st.session_state.get("dnd_budget_team_id")

        if mgr and set(current_ids) == set(mgr.get("squad_ids", [])):
            # A synced FPL squad may cost more than £100m at today's prices.
            # Keep the real bank rather than blocking the user's own team.
            dnd_budget_tenths = max(
                1000,
                initial_cost + int(round(float(mgr.get("bank") or 0) * 10)),
            )
            st.session_state["dnd_budget_tenths"] = dnd_budget_tenths
            st.session_state["dnd_budget_team_id"] = mgr.get("team_id")
        elif stored_budget is not None and mgr and stored_team == mgr.get("team_id"):
            # Keep the synced team's budget after edits; recomputing from the
            # edited squad would incorrectly reset it to £100m mid-session.
            dnd_budget_tenths = int(stored_budget)
        else:
            # For saved/new squads, allow at least the current value to avoid
            # blocking a squad whose prices have risen above £100m.
            dnd_budget_tenths = max(1000, initial_cost)

        if "dnd_version" not in st.session_state:
            st.session_state["dnd_version"] = 0

        try:
            from fpl.components.squad_builder import squad_builder

            component_value = squad_builder(
                players=[compact_player(p) for p in players],
                selected=current_selected,
                budget=dnd_budget_tenths,
                club_max=3,
                version=int(st.session_state.get("dnd_version", 0)),
                key="squad_builder_dnd",
            )
        except Exception as exc:  # component missing/unbuilt -> keep the app usable
            st.warning(f"Komponen drag & drop tidak tersedia: {exc}. Memakai mode Daftar.")
            dnd_mode = False
            component_value = None

        if dnd_mode and component_value is not None:
            parsed = normalize_selected(component_value)
            signature = tuple(selected_ids(parsed))
            revision = component_value.get("_revision") if isinstance(component_value, dict) else None
            if revision is not None:
                should_process = revision != st.session_state.get("_dnd_revision")
            else:
                # Backward-compatible fallback for an older cached frontend.
                should_process = signature != st.session_state.get("_dnd_signature")

            if should_process:
                if revision is not None:
                    st.session_state["_dnd_revision"] = revision
                st.session_state["_dnd_signature"] = signature
                errors = validate_selection(
                    parsed,
                    by_id,
                    budget=dnd_budget_tenths,
                    club_max=3,
                )
                if errors:
                    st.session_state["dnd_error"] = errors
                    st.session_state["dnd_version"] = int(st.session_state.get("dnd_version", 0)) + 1
                    st.rerun()
                else:
                    st.session_state["dnd_error"] = None
                    flat = selected_ids(parsed)
                    st.session_state["squad"] = flat
                    for pos in SQUAD_SIZE:
                        st.session_state[f"sel_{pos}"] = labels_for(pos, flat)
                    sel_new = flat
                    # Re-render the component with the freshly validated
                    # selection. The revision guard prevents a loop.
                    st.rerun()

        if dnd_mode:
            if st.session_state.get("dnd_error"):
                st.error("Drop ditolak: " + "; ".join(st.session_state["dnd_error"]))
            st.caption(
                "Tarik pemain dari kandidat ke posisi yang sesuai, atau klik tombol **+** / **×**. "
                "Aturan 2 GK / 5 DEF / 5 MID / 3 FWD, maksimal 3 pemain per klub, dan budget otomatis dicek."
            )
            if not sel_new:
                sel_new = selected_ids_from_widgets()

    if not dnd_mode:
        st.session_state.pop("dnd_error", None)
        cols = st.columns(4)
        for col, (pos, need) in zip(cols, SQUAD_SIZE.items()):
            with col:
                chosen = st.multiselect(
                    f"Pilih {need} pemain {pos}",
                    list(pos_options[pos].keys()),
                    key=f"sel_{pos}",
                    placeholder=f"Maks {need} pemain",
                )
                ids = [pos_options[pos][opt] for opt in chosen if opt in pos_options[pos]]
                sel_new += ids
                st.caption(f"{len(ids)}/{need} dipilih")

    total_cost = sum(by_id[i]["price"] for i in sel_new) / 10
    if dnd_mode and dnd_budget_tenths is not None:
        bank = max(0.0, (dnd_budget_tenths - int(round(total_cost * 10))) / 10)
    else:
        bank = 100.0 - total_cost

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total skuad", f"{len(sel_new)}/15")
    c2.metric("Nilai tim", f"£{total_cost:.1f}m")
    c3.metric("Sisa budget", f"£{bank:.1f}m")
    with c4:
        if st.button("💾 Simpan Tim", disabled=len(sel_new) != 15, use_container_width=True):
            save_squad(sel_new)
            st.session_state["squad"] = sel_new
            st.toast("✅ Skuad 15 pemain berhasil disimpan!", icon="💾")
            st.success("✅ Skuad 15 pemain berhasil disimpan secara permanen!")
            st.rerun()

# If the expander content did not define a selection, fall back to the
# widget-backed selection (not the saved squad, which may be stale).
if "sel_new" not in dir():
    sel_new = selected_ids_from_widgets()
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
            "chance_this": p.get("chance_this"),
            "chance_next": p.get("chance_next", p.get("chance")),
            "news": p.get("news", ""),
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

    auto_result = best_xi(squad)

    if auto_result:
        from fpl.lineup import (
            build_lineup_result,
            compact_lineup_player,
            default_lineup,
            normalize_component_value,
            validate_lineup,
        )

        squad_by_id = {int(p["id"]): p for p in squad}
        lineup_signature = tuple(sorted(squad_by_id))
        if st.session_state.get("lineup_signature") != lineup_signature:
            auto_xi, auto_bench_out, auto_bench_gk = default_lineup(auto_result)
            st.session_state["lineup_signature"] = lineup_signature
            st.session_state["lineup_xi"] = auto_xi
            st.session_state["lineup_bench_out"] = auto_bench_out
            st.session_state["lineup_bench_gk"] = auto_bench_gk
            st.session_state["lineup_version"] = int(st.session_state.get("lineup_version", 0)) + 1
            st.session_state.pop("lineup_error", None)

        xi_ids = list(st.session_state.get("lineup_xi") or [])
        bench_out_ids = list(st.session_state.get("lineup_bench_out") or [])
        bench_gk_id = st.session_state.get("lineup_bench_gk")
        lineup_errors = validate_lineup(xi_ids, bench_out_ids, bench_gk_id, squad_by_id)
        if lineup_errors:
            auto_xi, auto_bench_out, auto_bench_gk = default_lineup(auto_result)
            xi_ids, bench_out_ids, bench_gk_id = auto_xi, auto_bench_out, auto_bench_gk
            st.session_state["lineup_xi"] = xi_ids
            st.session_state["lineup_bench_out"] = bench_out_ids
            st.session_state["lineup_bench_gk"] = bench_gk_id
            st.session_state["lineup_version"] = int(st.session_state.get("lineup_version", 0)) + 1

        result = build_lineup_result(xi_ids, bench_out_ids, bench_gk_id, squad_by_id)
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
            c_auto, _c_spacer = st.columns([1, 3])
            with c_auto:
                if st.button("🔄 Auto XI", use_container_width=True, key="auto_xi_btn"):
                    auto_xi, auto_bench_out, auto_bench_gk = default_lineup(auto_result)
                    st.session_state["lineup_xi"] = auto_xi
                    st.session_state["lineup_bench_out"] = auto_bench_out
                    st.session_state["lineup_bench_gk"] = auto_bench_gk
                    st.session_state["lineup_version"] = int(st.session_state.get("lineup_version", 0)) + 1
                    st.session_state.pop("lineup_error", None)
                    st.rerun()

            lineup_component_ok = False
            lineup_value = None
            try:
                from fpl.components.lineup_builder import lineup_builder

                lineup_payload = [
                    compact_lineup_player(p, lineup_gw_cells(p, gw_projs))
                    for p in squad
                ]
                lineup_value = lineup_builder(
                    players=lineup_payload,
                    xi=xi_ids,
                    bench_out=bench_out_ids,
                    bench_gk=bench_gk_id,
                    version=int(st.session_state.get("lineup_version", 0)),
                    key="lineup_builder",
                )
                lineup_component_ok = True
            except Exception as exc:
                st.warning(f"Komponen pitch drag & drop tidak tersedia: {exc}. Memakai tampilan statis.")

            if st.session_state.get("lineup_error"):
                st.error("Lineup ditolak: " + "; ".join(st.session_state["lineup_error"]))

            if lineup_component_ok and lineup_value is not None:
                parsed = normalize_component_value(lineup_value)
                if parsed is not None:
                    errors = validate_lineup(
                        parsed["xi"],
                        parsed["bench_out"],
                        parsed["bench_gk"],
                        squad_by_id,
                    )
                    sig = (tuple(parsed["xi"]), tuple(parsed["bench_out"]), parsed["bench_gk"])
                    revision = lineup_value.get("_revision") if isinstance(lineup_value, dict) else None
                    if revision is not None:
                        should_process = revision != st.session_state.get("_lineup_revision")
                    else:
                        should_process = sig != st.session_state.get("_lineup_sig")

                    if should_process:
                        if revision is not None:
                            st.session_state["_lineup_revision"] = revision
                        st.session_state["_lineup_sig"] = sig
                        if errors:
                            st.session_state["lineup_error"] = errors
                            st.session_state["lineup_version"] = int(st.session_state.get("lineup_version", 0)) + 1
                            st.rerun()
                        else:
                            st.session_state["lineup_error"] = None
                            st.session_state["lineup_xi"] = parsed["xi"]
                            st.session_state["lineup_bench_out"] = parsed["bench_out"]
                            st.session_state["lineup_bench_gk"] = parsed["bench_gk"]
                            st.rerun()

            if not lineup_component_ok:
                # Static fallback when the JS component cannot be loaded.
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

        # Keep full rows: availability filters (status/news/chance) are now
        # part of the transfer engine, so stripping them would hide injuries.
        pool_t = players

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
                st.html(
                    transfer_card_html(
                        w,
                        best_rep,
                        s["player_total"],
                        best_rep["proj_total"],
                        s["gain"],
                        extra_badges=f"{hit_badge}{swing_html}",
                    )
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
                st.html(transfer_card_html(w, best_rep, w_proj, rep_proj, s["gain"]))
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
            
            ai_out_av = availability(ai_w)
            ai_in_av = availability(ai_rep)
            reasoning = f"**AI Assistant:** Berdasarkan analisis prediktif algoritma kami, melepas **{ai_w['web_name']}** (£{ai_w['price']/10:.1f}m) adalah keputusan terbaik minggu ini (potensi 3 GW hanya {top_ai['player_total']:.1f} poin). "
            reasoning += f"Sebagai gantinya, masukkan **{ai_rep['web_name']}** (£{ai_rep['price']/10:.1f}m) yang sedang dalam momentum bagus dengan jadwal mendukung (proyeksi 3 GW: {top_ai['reps'][0]['proj_total']:.1f} poin). "
            if ai_out_av["pct"] < 100:
                reasoning += f"Alasan tambahan: **{ai_w['web_name']}** berstatus {ai_out_av['label']} — {ai_out_av['news'] or 'peluang main tidak penuh'}. "
            if ai_in_av["pct"] < 100:
                reasoning += f"Catatan risiko: pengganti hanya {ai_in_av['label']}. "
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
