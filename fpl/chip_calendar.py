"""Season-aware chip calendar (TC / BB / FH / WC).

The existing ``chips_ev`` module prices chips for the *next* Gameweek only.
That is useful for "should I play it now?", but not for "which Gameweek in the
next two months is the best TC/BB/FH spot?".  This module builds a lightweight
calendar from the same projection engine:

* Double/blank Gameweeks and fixture counts come from the FPL fixture list.
* Player values per future GW come from ``fpl.horizon.future_proj`` (same
  formula as the main model, including DGW summing).
* The current squad (or a reference squad) is used for TC/BB/FH/WC estimates.

It is deliberately a *planning heuristic*, not a full stochastic optimiser;
the existing chip EV page remains the final check for the current GW.
"""

from __future__ import annotations

import math
from collections import Counter

from . import planner
from .horizon import future_proj


def _val(value):
    try:
        f = float(value)
        if math.isnan(f):
            return 0.0
        return max(0.0, f)
    except (TypeError, ValueError):
        return 0.0


def _pool(df, squad_ids, limit=180):
    """Relevant players for market comparisons: squad + top current projections."""
    rows = []
    seen = set()
    by_id = {int(r["id"]): r for r in df.to_dict("records")}
    for pid in squad_ids or []:
        r = by_id.get(int(pid))
        if r is not None and pid not in seen:
            rows.append(r)
            seen.add(pid)
    ranked = (
        df.dropna(subset=["proj"])
        .sort_values("proj", ascending=False)
        .head(max(0, int(limit) - len(rows)))
        .to_dict("records")
    )
    for r in ranked:
        pid = int(r["id"])
        if pid not in seen:
            rows.append(r)
            seen.add(pid)
    return rows


def _market_xi_value(pool_rows, values, pos_of, budget=1000):
    """Best greedy XI from the market under position/club/budget limits."""
    if not pool_rows:
        return 0.0
    tmp = []
    for r in pool_rows:
        row = dict(r)
        row["proj"] = _val(values.get(int(r["id"]), 0.0))
        tmp.append(row)
    tmp.sort(key=lambda r: r.get("proj", 0), reverse=True)
    picked = []
    counts = Counter()
    club = Counter()
    cost = 0
    max_pos = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
    min_pos = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}

    def _can_add(r):
        pos = r.get("pos", "MID")
        team = int(r.get("team", 0))
        price = int(r.get("price", 0) or 0)
        return (
            counts[pos] < max_pos[pos]
            and club[team] < 3
            and cost + price <= budget
        )

    def _add(r):
        nonlocal cost
        pos = r.get("pos", "MID")
        team = int(r.get("team", 0))
        cost += int(r.get("price", 0) or 0)
        picked.append(r)
        counts[pos] += 1
        club[team] += 1

    for r in tmp:
        if len(picked) >= 11 and all(counts[p] >= min_pos[p] for p in min_pos):
            break
        if _can_add(r):
            _add(r)

    # Fill any missing minimum slots with the cheapest legal players.
    if len(picked) < 11:
        used = {int(r["id"]) for r in picked}
        for pos in ("GK", "DEF", "MID", "FWD"):
            while counts[pos] < min_pos[pos]:
                candidates = [
                    r for r in tmp
                    if int(r["id"]) not in used and r.get("pos") == pos and _can_add(r)
                ]
                if not candidates:
                    return 0.0
                r = min(candidates, key=lambda x: int(x.get("price", 0) or 0))
                _add(r)
                used.add(int(r["id"]))

    if len(picked) < 11 or any(counts[p] < min_pos[p] for p in min_pos):
        return 0.0
    return sum(float(r["proj"]) for r in picked)


def build_chip_calendar(gd, df, state, horizon=12, market_limit=160):
    """Return a per-GW chip opportunity table + one-chip-per-GW sequence.

    Args:
        gd: GameData
        df: projection table (current GW)
        state: planner.manager_state / fallback state
        horizon: number of upcoming GWs to inspect
        market_limit: size of the market pool used for FH/WC comparisons

    Returns:
        dict with ``by_gw`` (all GW rows) and ``best`` (best GW per chip),
        plus a conflict-free ``calendar`` list.
    """
    current = int(gd.next_event["id"])
    end = min(38, current + max(1, int(horizon)) - 1)
    events = [e for e in gd.events if current <= int(e["id"]) <= end]
    if not events:
        events = [gd.next_event]

    squad_ids = [int(x) for x in (state.get("squad_ids") or [])]
    pos_of = {int(r["id"]): r.get("pos", "MID") for r in df.to_dict("records")}
    pool = _pool(df, squad_ids, limit=market_limit)
    budget = int(state.get("bank") or 0) + sum(
        int(v or 0) for v in (state.get("sell_prices") or {}).values()
    )
    if budget <= 0:
        budget = 1000
    squad_rows = [r for r in df.to_dict("records") if int(r["id"]) in set(squad_ids)]
    if not squad_rows or len(squad_rows) != 15:
        # Fallback: use the reference XI plus the best available fillers.
        squad_rows = sorted(
            [r for r in df.to_dict("records") if r.get("proj")],
            key=lambda r: r.get("proj") or 0,
            reverse=True,
        )[:15]
        squad_ids = [int(r["id"]) for r in squad_rows]

    # Compute future values once per GW for the relevant pool.
    values_by_gw = {}
    for ev in events:
        gw = int(ev["id"])
        if gw == current:
            values_by_gw[gw] = {
                int(r["id"]): _val(r.get("proj")) for r in pool
            }
            continue
        vals = {}
        steps = gw - current
        for r in pool:
            try:
                v = future_proj(r, gd, gw, steps_ahead=steps)
            except Exception:
                v = None
            vals[int(r["id"])] = _val(v)
        values_by_gw[gw] = vals

    by_gw = []
    for ev in events:
        gw = int(ev["id"])
        values = values_by_gw[gw]
        counts = gd.team_fixture_counts(gw)
        dgw_teams = [tid for tid, n in counts.items() if n >= 2]
        bgw_teams = [tid for tid in gd.teams_by_id if counts.get(tid, 0) == 0]

        squad_vals = {pid: _val(values.get(pid, 0.0)) for pid in squad_ids}
        xi = planner.xi_value(squad_ids, squad_vals, pos_of, captain_mult=1.0)
        total15 = sum(squad_vals.values())
        bench = max(0.0, total15 - xi)
        tc_extra = max(squad_vals.values(), default=0.0)

        market_xi = _market_xi_value(pool, values, pos_of, budget=budget)
        fh_gain = max(0.0, market_xi - xi)

        # WC heuristic: average FH-like gain over the next 3 GWs plus a
        # small bonus for a DGW / big fixture swing.
        window = []
        for ev2 in events:
            gw2 = int(ev2["id"])
            if gw <= gw2 < gw + 3:
                window.append(values_by_gw[gw2])
        wc_gain = 0.0
        if window:
            for vals2 in window:
                wc_gain += max(0.0, market_xi - planner.xi_value(
                    squad_ids,
                    {pid: _val(vals2.get(pid, 0.0)) for pid in squad_ids},
                    pos_of,
                    captain_mult=1.0,
                ))
            wc_gain /= len(window)
        wc_gain += 1.5 * len(dgw_teams)

        by_gw.append({
            "gw": gw,
            "dgw": dgw_teams,
            "bgw": bgw_teams,
            "tc": round(tc_extra, 2),
            "bb": round(bench, 2),
            "fh": round(fh_gain, 2),
            "wc": round(wc_gain, 2),
            "xi": round(xi, 2),
            "total15": round(total15, 2),
        })

    # Best GW per chip, limited to chips still available in the current set.
    available = set((state.get("chips") or {}).get("available_now") or [])
    best = {}
    for chip, key in (("TC", "tc"), ("BB", "bb"), ("FH", "fh"), ("WC", "wc")):
        if available and chip not in available:
            continue
        row = max(by_gw, key=lambda r: r.get(key, 0.0))
        best[chip] = {
            "gw": row["gw"],
            "score": row[key],
            "dgw": row["dgw"],
            "bgw": row["bgw"],
        }

    # One chip per GW: assign in descending score order, skipping conflicts.
    calendar = []
    used = set()
    for chip in sorted(best, key=lambda c: best[c]["score"], reverse=True):
        row = best[chip]
        gw = row["gw"]
        if gw in used:
            alternatives = sorted(
                [r for r in by_gw if r["gw"] not in used],
                key=lambda r: r.get({"TC": "tc", "BB": "bb", "FH": "fh", "WC": "wc"}[chip], 0.0),
                reverse=True,
            )
            if not alternatives:
                continue
            gw = alternatives[0]["gw"]
            row = {
                "gw": gw,
                "score": alternatives[0][{"TC": "tc", "BB": "bb", "FH": "fh", "WC": "wc"}[chip]],
                "dgw": alternatives[0]["dgw"],
                "bgw": alternatives[0]["bgw"],
            }
        used.add(gw)
        calendar.append({"chip": chip, **row})

    calendar.sort(key=lambda r: r["gw"])
    return {
        "current_gw": current,
        "horizon": len(events),
        "by_gw": by_gw,
        "best": best,
        "calendar": calendar,
        "chips": state.get("chips") or {},
    }
