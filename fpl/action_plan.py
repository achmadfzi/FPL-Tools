"""Shared Gameweek action-plan builder.

The old Beranda and Rencana Aksi pages computed overlapping pieces
separately.  This module is the single service used by both, so the summary
card and the detailed page can never disagree about the captain, transfer
plan, or chip recommendation.
"""

from __future__ import annotations

import time


def fallback_state(df, gw_id=None):
    """Best-effort state when no FPL team is connected."""
    from .simulator import load_saved_squad, reference_xi

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
        "chips": {
            "available_now": [], "next_set": [], "expires_gw": 19,
            "current_gw": int(gw_id or 1),
        },
        "gw_synced": None,
        "synced_at": None,
        "_source": source,
        "_pos_of": pos_of,
    }


def build_action_plan(gd, df, gw_id=None, n_sim=400, horizon=6, include_calendar=True):
    """Build every decision the dashboard needs for one Gameweek.

    Returns a dict with ``state``, ``line`` (EV-optimal XI/bench plus the
    projection-based captain and EV comparison), ``plan`` (multi-GW
    transfers), ``chips``, and ``chip_calendar``.
    """
    from . import chips_ev, planner
    from .chip_calendar import build_chip_calendar
    from .horizon import player_gw_projections
    from .simulator import optimal_lineup, simulate_squad_matrices

    gw_id = int(gw_id or gd.next_event["id"])
    state = planner.manager_state(df, current_gw=gw_id)
    source = "Tim FPL terhubung"
    if state is None:
        state = fallback_state(df, gw_id)
        source = state.pop("_source", "skuad tersimpan")
        state.pop("_pos_of", None)
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

    chip_calendar = None
    if include_calendar:
        try:
            chip_calendar = build_chip_calendar(gd, df, state, horizon=12)
        except Exception:
            chip_calendar = None

    return {
        "state": state,
        "source": source,
        "line": line,
        "plan": plan,
        "chips": chips,
        "chip_calendar": chip_calendar,
        "gw": gw_id,
        "computed_at": time.time(),
    }


def first_transfer(plan):
    """Return the first non-empty transfer step, or None."""
    for step in (plan or {}).get("plan", []):
        if step.get("transfers"):
            return step
    return None


def confidence_for_captain(line, captain_analysis=None):
    """Plain-language confidence for the captain recommendation."""
    cap = (line or {}).get("captain") or {}
    if not cap:
        return "Rendah"
    p_play = float(cap.get("p_play") or 0)
    p_blank = float(cap.get("p_blank") or 0)
    if p_play >= 0.95 and p_blank <= 0.05:
        return "Tinggi"
    if p_play >= 0.75:
        return "Sedang"
    return "Rendah"


def confidence_for_transfer(plan, state):
    """Plain-language confidence for the transfer recommendation."""
    first = first_transfer(plan)
    if not first:
        return "Tinggi"
    gain = float((plan or {}).get("gain") or 0.0)
    hits = int(first.get("hits") or 0)
    if hits > 0:
        return "Rendah"
    if gain >= 4.0:
        return "Tinggi"
    if gain >= 1.5:
        return "Sedang"
    return "Rendah"
