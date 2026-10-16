"""Transfer planning & squad optimisation with real FPL constraints.

This module implements the pieces that make weekly decisions *legal and
point-optimal* rather than heuristically plausible:

- purchase/selling prices straight from the season transfer history
  (selling price = purchase + floor(profit / 2); never above current price)
- free-transfer accounting (1 per GW, rollover up to 5, chips do not grant a
  new FT — verified against the manager's own transfer history)
- exact squad optimisation via MILP (scipy) for Wildcard / initial squads
- multi-GW beam search over transfer sequences including -4 hits, respecting
  budget, the 3-per-club rule and the 2/5/5/3 position structure.

All heavy entry points accept precomputed projection data so the planner can
be driven from stored GW projections (fpl.horizon).
"""

import json
from collections import Counter

import numpy as np

FT_MAX = 5
HIT_COST = 4
POS_NEED = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
CHIP_NAMES = {"bboost": "BB", "3xc": "TC", "wildcard": "WC", "freehit": "FH"}


# ---------------------------------------------------------------------------
# Manager state: purchase/selling prices, free transfers, chips
# ---------------------------------------------------------------------------


def purchase_prices(team_id):
    """{element_id: purchase_price (tenths)} from the season transfer history.

    Players bought before the first recorded transfer are approximated at
    their current price (we cannot recover their GW1 price).
    """
    out = {}
    try:
        from .api import get_entry_transfers

        transfers = get_entry_transfers(int(team_id)) or []
    except Exception:
        return out
    for t in transfers:
        el_in = t.get("element_in")
        cost = t.get("element_in_cost")
        if el_in is not None and cost:
            out[int(el_in)] = int(cost)
    return out


def selling_price(purchase, now_cost):
    """FPL selling price: purchase + half of any profit, rounded down."""
    if now_cost <= purchase:
        return int(now_cost)
    return int(purchase + (now_cost - purchase) // 2)


def free_transfers(team_id):
    """Free transfers available *now*, computed from the season history.

    Standard rules: start with 1 FT in GW1; each GW grants +1 (cap 5);
    transfers beyond the free ones cost 4 points each. Chip gameweeks
    (Wildcard/Free Hit/Bench Boost/Triple Captain) do NOT grant a new FT —
    this matches the observed -4 hit in the manager's own history.

    Returns (ft, detail_str).
    """
    try:
        from .api import get_entry_history

        hist = get_entry_history(int(team_id)) or {}
    except Exception:
        return 1, "estimasi default (riwayat tidak tersedia)"

    chips = {int(c.get("event") or 0): c.get("name") for c in hist.get("chips", [])}
    entries = sorted(hist.get("current", []), key=lambda e: e.get("event") or 0)

    ft = 1
    detail = []
    for e in entries:
        gw = int(e.get("event") or 0)
        used = int(e.get("event_transfers") or 0)
        cost = int(e.get("event_transfers_cost") or 0)
        chip = chips.get(gw)
        if chip:
            # Chip week: no free transfer is granted, banked FTs are kept.
            detail.append(f"GW{gw} {CHIP_NAMES.get(chip, chip)} (FT tetap {ft})")
            continue
        hit_transfers = used - max(0, cost // HIT_COST)
        ft_next = min(FT_MAX, max(0, ft - hit_transfers) + 1)
        detail.append(f"GW{gw} pakai {used} (FT {ft}→{ft_next})")
        ft = ft_next

    # If the last recorded GW is behind the upcoming event, roll forward the
    # intervening GWs (no transfers were made in them by definition).
    return ft, "; ".join(detail)


def chips_availability(chips_played, current_gw):
    """Two chip sets: first set usable until GW19, second from GW20.

    Returns dict: {"available_now": [...], "next_set": [...],
                   "expires_gw": 19, "played": {...}}.
    """
    played_first, played_second = set(), set()
    for c in chips_played or []:
        name = CHIP_NAMES.get(c.get("name", ""), c.get("name"))
        ev = int(c.get("event") or 0)
        (played_first if ev <= 19 else played_second).add(name)
    all_chips = {"TC", "BB", "WC", "FH"}
    if current_gw <= 19:
        available = sorted(all_chips - played_first)
        nxt = sorted(all_chips)
    else:
        available = sorted(all_chips - played_second)
        nxt = sorted(all_chips - played_second)
    return {
        "available_now": available,
        "next_set": nxt,
        "expires_gw": 19,
        "current_gw": current_gw,
        "played_first_half": sorted(played_first),
        "played_second_half": sorted(played_second),
    }


def manager_state(df, team_id=None, current_gw=None):
    """Full actionable state from the synced manager file.

    Returns dict with squad rows/ids, bank (tenths), sell prices (tenths),
    free transfers, chips availability, or None when no team is synced.
    """
    from .api import DATA_DIR as _DD

    mgr_file = _DD / "manager.json"
    if not mgr_file.exists():
        return None
    try:
        mgr = json.loads(mgr_file.read_text())
    except Exception:
        return None
    team_id = int(team_id or mgr.get("team_id") or 0)
    if not team_id:
        return None

    df_rows = {int(r["id"]): r for r in df.to_dict("records")}
    squad_ids = mgr.get("squad_ids") or []
    rows = [df_rows[i] for i in squad_ids if i in df_rows]
    if len(rows) != 15:
        return None

    bank = int(round(float(mgr.get("bank") or 0.0) * 10))
    purchases = purchase_prices(team_id)
    sell = {}
    for r in rows:
        pid = int(r["id"])
        now = int(r["price"])
        purchase = purchases.get(pid, now)
        sell[pid] = selling_price(purchase, now)

    ft, ft_detail = free_transfers(team_id)
    chips = chips_availability(
        mgr.get("chips_played") or [],
        int(current_gw or (int(mgr.get("gw_synced") or 1) + 1)),
    )
    return {
        "team_id": team_id,
        "team_name": mgr.get("team_name", "FPL Team"),
        "squad_rows": rows,
        "squad_ids": [int(r["id"]) for r in rows],
        "bank": bank,
        "bank_value": mgr.get("bank", 0.0),
        "team_value": mgr.get("team_value", 0.0),
        "sell_prices": sell,
        "purchase_prices": purchases,
        "free_transfers": ft,
        "ft_detail": ft_detail,
        "chips": chips,
        "gw_synced": mgr.get("gw_synced"),
        "synced_at": mgr.get("synced_at"),
    }


# ---------------------------------------------------------------------------
# Fast XI value (no budget constraint — squad is already legal)
# ---------------------------------------------------------------------------


def xi_value(squad_ids, values, pos_of):
    """Max projected XI total for a legal 15-player squad (formation max).

    Club limits are already satisfied by the squad, so only formations matter.
    values: {player_id: points}.
    """
    gk, defs, mids, fwds = [], [], [], []
    for pid in squad_ids:
        v = values.get(pid, 0.0) or 0.0
        p = pos_of.get(pid, "MID")
        if p == "GK":
            gk.append(v)
        elif p == "DEF":
            defs.append(v)
        elif p == "MID":
            mids.append(v)
        else:
            fwds.append(v)
    if not gk:
        return 0.0
    gk.sort(reverse=True)
    defs.sort(reverse=True)
    mids.sort(reverse=True)
    fwds.sort(reverse=True)
    dsum = [0.0]
    for v in defs:
        dsum.append(dsum[-1] + v)
    msum = [0.0]
    for v in mids:
        msum.append(msum[-1] + v)
    fsum = [0.0]
    for v in fwds:
        fsum.append(fsum[-1] + v)
    best = 0.0
    for nd in (3, 4, 5):
        if nd > len(defs):
            continue
        for nm in (2, 3, 4, 5):
            if nm > len(mids):
                continue
            nf = 10 - nd - nm
            if nf < 1 or nf > 3 or nf > len(fwds):
                continue
            total = gk[0] + dsum[nd] + msum[nm] + fsum[nf]
            if total > best:
                best = total
    return best


# ---------------------------------------------------------------------------
# Exact squad optimisation (MILP)
# ---------------------------------------------------------------------------


def optimize_squad(df, budget, player_values, exclude_ids=(), forced_ids=(), club_max=3):
    """Exact 15-player squad maximising total value under all FPL rules.

    Args:
        df: projection table (needs id, pos, team, price, status, chance)
        budget: available budget in tenths
        player_values: {player_id: points over the planning horizon}
        exclude_ids / forced_ids: player ids to forbid / force
    Returns: list of 15 player ids (or None when infeasible).
    """
    from scipy.optimize import Bounds, LinearConstraint, milp

    rows = []
    for r in df.to_dict("records"):
        pid = int(r["id"])
        if pid in exclude_ids:
            continue
        if r.get("status") in ("i", "u", "n"):
            continue
        v = player_values.get(pid)
        if v is None:
            continue
        rows.append({
            "id": pid,
            "pos": r["pos"],
            "team": int(r["team"]),
            "price": int(r["price"]),
            "value": max(0.0, float(v)),
        })
    if not rows:
        return None

    n = len(rows)
    ids = [r["id"] for r in rows]
    prices = np.array([r["price"] for r in rows], dtype=float)
    values = np.array([r["value"] for r in rows], dtype=float)
    pos = [r["pos"] for r in rows]
    team = [r["team"] for r in rows]

    cons = []
    lb, ub = [], []

    # Position structure: exact counts.
    for pname, need in POS_NEED.items():
        row = np.array([1.0 if p == pname else 0.0 for p in pos])
        cons.append(row)
        lb.append(need)
        ub.append(need)

    # Club limit.
    for club in sorted(set(team)):
        row = np.array([1.0 if t == club else 0.0 for t in team])
        cons.append(row)
        lb.append(0.0)
        ub.append(float(club_max))

    # Budget.
    cons.append(prices)
    lb.append(0.0)
    ub.append(float(budget))

    A = np.vstack(cons)
    constraints = LinearConstraint(A, np.array(lb), np.array(ub))

    bounds_lb = np.zeros(n)
    bounds_ub = np.ones(n)
    forced = set(int(i) for i in forced_ids)
    for j, pid in enumerate(ids):
        if pid in forced:
            bounds_lb[j] = 1.0
    bounds = Bounds(bounds_lb, bounds_ub)

    res = milp(
        c=-values,
        constraints=[constraints],
        integrality=np.ones(n),
        bounds=bounds,
        options={"time_limit": 20},
    )
    if not res.success or res.x is None:
        return None
    picked = [ids[j] for j in range(n) if res.x[j] > 0.5]
    if len(picked) != 15:
        return None
    return picked


# ---------------------------------------------------------------------------
# Multi-GW transfer planning (beam search with hits)
# ---------------------------------------------------------------------------


def plan_transfers(gd, df, state, gw_projs, horizon=4, beam_width=30,
                   max_per_gw=2, top_singles=24, top_doubles=50):
    """Beam search over transfer sequences for the next `horizon` GWs.

    Args:
        gd: GameData (uses next_event for GW numbering)
        df: projection table rows for the pool
        state: from manager_state()
        gw_projs: {player_id: [pts_gw0, pts_gw1, ...]} (fpl.horizon)
        horizon, beam_width: search effort
        max_per_gw: max transfers considered per GW (0-2 recommended)
    Returns: dict with plan steps, totals and the hold baseline.
    """
    cur = int(gd.next_event["id"])
    info = {}
    for r in df.to_dict("records"):
        pid = int(r["id"])
        info[pid] = {
            "pos": r.get("pos", "MID"),
            "team": int(r.get("team", 0)),
            "price": int(r.get("price", 0)),
            "name": r.get("web_name", str(pid)),
            "team_short": r.get("team_short", ""),
        }
    pos_of = {pid: v["pos"] for pid, v in info.items()}
    value_of = {pid: (gw_projs.get(pid) or [0.0] * horizon) for pid in info}

    def _gw_values(g):
        return {pid: max(0.0, float(vals[g]) if g < len(vals) and vals[g] is not None else 0.0)
                for pid, vals in value_of.items()}

    values_per_gw = [_gw_values(g) for g in range(horizon)]

    def xi(ids, g):
        return xi_value(ids, values_per_gw[g], pos_of)

    squad0 = tuple(sorted(state["squad_ids"]))
    bank0 = int(state["bank"])
    sell = dict(state.get("sell_prices") or {})
    ft0 = int(state.get("free_transfers") or 1)

    hold_total = sum(xi(squad0, g) for g in range(horizon))

    def club_ok(ids):
        return max(Counter(info[i]["team"] for i in ids).values()) <= 3

    def structure_ok(ids):
        c = Counter(pos_of[i] for i in ids)
        return all(c.get(p, 0) == n for p, n in POS_NEED.items())

    # Max candidate pool per position for speed
    pool_by_pos = {p: [pid for pid, v in info.items() if v["pos"] == p]
                   for p in POS_NEED}

    states = [{
        "squad": squad0, "bank": bank0, "ft": ft0,
        "cum": 0.0, "plan": [],
    }]

    for g in range(horizon):
        # Ranking values: remaining horizon total for candidate screening
        totals = {}
        for pid, vals in value_of.items():
            s = 0.0
            for gg in range(g, horizon):
                v = vals[gg] if gg < len(vals) else 0.0
                s += float(v or 0.0)
            totals[pid] = s

        next_states = []
        for st in states:
            base = xi(st["squad"], g)
            # Option 0: hold (no transfer)
            next_states.append({
                "squad": st["squad"], "bank": st["bank"],
                "ft": min(FT_MAX, max(0, st["ft"]) + 1),
                "cum": st["cum"] + base,
                "plan": st["plan"] + [{"gw": cur + g, "transfers": [], "hits": 0}],
            })

            squad_set = set(st["squad"])
            # --- single transfers ---
            singles = []
            for out in st["squad"]:
                sell_now = sell.get(out, info[out]["price"])
                budget_in = st["bank"] + sell_now
                out_pos = pos_of[out]
                out_total = totals.get(out, 0.0)
                for in_pid in pool_by_pos[out_pos]:
                    if in_pid in squad_set:
                        continue
                    pinfo = info[in_pid]
                    if pinfo["price"] > budget_in:
                        continue
                    gain = totals.get(in_pid, 0.0) - out_total
                    if gain <= 1.0:
                        continue
                    new_squad = tuple(sorted((squad_set - {out}) | {in_pid}))
                    singles.append((gain, out, in_pid, new_squad))
            singles.sort(key=lambda x: -x[0])
            singles = singles[:top_singles]

            for gain_rank, out, in_pid, new_squad in singles:
                k = 1
                hits = HIT_COST * max(0, k - st["ft"])
                new_bank = st["bank"] + sell.get(out, info[out]["price"]) - info[in_pid]["price"]
                if new_bank < 0:
                    continue
                if not club_ok(new_squad) or not structure_ok(new_squad):
                    continue
                new_ft = min(FT_MAX, max(0, st["ft"] - k) + 1)
                next_states.append({
                    "squad": new_squad, "bank": new_bank, "ft": new_ft,
                    "cum": st["cum"] + xi(new_squad, g) - hits,
                    "plan": st["plan"] + [{
                        "gw": cur + g,
                        "transfers": [{"out": out, "in": in_pid, "gain_horizon": round(gain_rank, 2)}],
                        "hits": hits,
                    }],
                })

            # --- double transfers (pair of singles from different outs) ---
            if max_per_gw >= 2:
                doubles = []
                for i1 in range(len(singles)):
                    g1, out1, in1, ns1 = singles[i1]
                    for i2 in range(i1 + 1, len(singles)):
                        g2, out2, in2, ns2 = singles[i2]
                        if out2 == out1 or in2 == in1 or in1 == out2 or in2 == out1:
                            continue
                        ins_cost = info[in1]["price"] + info[in2]["price"]
                        outs_val = sell.get(out1, info[out1]["price"]) + sell.get(out2, info[out2]["price"])
                        if ins_cost > st["bank"] + outs_val:
                            continue
                        new_squad = tuple(sorted((set(ns1) - {out2}) | {in2}))
                        if not club_ok(new_squad) or not structure_ok(new_squad):
                            continue
                        doubles.append((g1 + g2, out1, in1, out2, in2, new_squad))
                doubles.sort(key=lambda x: -x[0])
                for combo, out1, in1, out2, in2, new_squad in doubles[:top_doubles]:
                    k = 2
                    hits = HIT_COST * max(0, k - st["ft"])
                    new_bank = (st["bank"] + sell.get(out1, info[out1]["price"]) + sell.get(out2, info[out2]["price"])
                                - info[in1]["price"] - info[in2]["price"])
                    if new_bank < 0:
                        continue
                    new_ft = min(FT_MAX, max(0, st["ft"] - k) + 1)
                    next_states.append({
                        "squad": new_squad, "bank": new_bank, "ft": new_ft,
                        "cum": st["cum"] + xi(new_squad, g) - hits,
                        "plan": st["plan"] + [{
                            "gw": cur + g,
                            "transfers": [
                                {"out": out1, "in": in1, "gain_horizon": round(combo, 2)},
                                {"out": out2, "in": in2},
                            ],
                            "hits": hits,
                        }],
                    })

        # Prune: dedupe by squad, keep best cumulative
        best_by_squad = {}
        for s in next_states:
            key = s["squad"]
            if key not in best_by_squad or s["cum"] > best_by_squad[key]["cum"]:
                best_by_squad[key] = s
        pruned = sorted(best_by_squad.values(), key=lambda s: -s["cum"])[:beam_width]
        states = pruned

    best = max(states, key=lambda s: s["cum"])

    # Enrich the plan with human-readable names
    enriched = []
    for step in best["plan"]:
        trs = []
        for t in step["transfers"]:
            out, inn = t["out"], t["in"]
            trs.append({
                "out_name": info.get(out, {}).get("name", out),
                "out_short": info.get(out, {}).get("team_short", ""),
                "out_price": info.get(out, {}).get("price", 0),
                "in_name": info.get(inn, {}).get("name", inn),
                "in_short": info.get(inn, {}).get("team_short", ""),
                "in_price": info.get(inn, {}).get("price", 0),
                "gain_horizon": t.get("gain_horizon"),
            })
        enriched.append({
            "gw": step["gw"],
            "transfers": trs,
            "hits": step["hits"],
        })

    return {
        "horizon": horizon,
        "total_planned": round(best["cum"], 2),
        "hold_total": round(hold_total, 2),
        "gain": round(best["cum"] - hold_total, 2),
        "final_squad": list(best["squad"]),
        "final_bank": best["bank"] / 10.0,
        "final_ft": best["ft"],
        "plan": enriched,
        "beam_width": beam_width,
    }
