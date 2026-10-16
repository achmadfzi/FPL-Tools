"""Chip expected-value estimation (TC / BB / FH / WC).

Point-estimate heuristics (the old fpl.strategy) cannot answer "is the chip
worth it *for this squad, this Gameweek*". Here every chip is priced with the
same Monte-Carlo engine used for captaincy and lineups:

- Triple Captain: extra EV of tripling the captain instead of doubling,
  including the vice-captain insurance when the captain blanks.
- Bench Boost: EV of the whole 15-man squad minus the auto-sub XI EV, i.e.
  exactly the points the bench adds.
- Free Hit: best possible XI from the market within the current selling
  budget versus the current squad's XI for that GW.
- Wildcard: optimal squad over the planning horizon versus holding the
  current squad (MILP under selling prices + bank).

Combined with the two-chip-set calendar (first set expires at the GW19
deadline, one chip per GW), the module ranks usable chips for the upcoming
Gameweek.
"""

from . import planner
from .simulator import optimal_lineup, simulate_squad_matrices


def _xi_proj(squad_ids, values, pos_of):
    return planner.xi_value(squad_ids, values, pos_of)


def evaluate_chips(gd, df, state, gw_projs, horizon=4, n=400, seed=11):
    """Price every remaining chip for the NEXT Gameweek.

    Args:
        gd, df: GameData + projection table
        state: fpl.planner.manager_state output
        gw_projs: {player_id: [pts per GW]} from fpl.horizon
        horizon: planning horizon for the Wildcard estimate
        n: simulation iterations for TC/BB

    Returns dict with per-chip estimates + the chip calendar status.
    """
    squad_rows = list(state["squad_rows"])
    squad_ids = list(state["squad_ids"])
    pos_of = {int(r["id"]): r.get("pos", "MID") for r in squad_rows}
    cur = int(gd.next_event["id"])

    # One shared simulation for BB + TC + optimal lineup.
    sim = simulate_squad_matrices(gd, df, squad_rows, n=n, seed=seed)
    line = optimal_lineup(gd, df, squad_rows, sim=sim)

    P, PL = sim["P"], sim["PL"]
    ids = sim["ids"]
    col = {pid: j for j, pid in enumerate(ids)}

    out = {"gw": cur, "n": n, "seed": seed}

    # ---------------- Triple Captain ----------------
    if "TC" in (state["chips"].get("available_now") or []):
        cap = line["captain"]
        ci = col[cap["id"]]
        # extra multiple vs normal captaincy = one more copy of the captain's
        # points when he plays (VC insurance is unaffected).
        tc_gain = float((P[:, ci] * PL[:, ci]).mean())
        out["TC"] = {
            "gain": round(tc_gain, 2),
            "captain": cap["web_name"],
            "team_short": cap.get("team_short"),
            "proj": cap.get("proj"),
            "p_plays": cap.get("p_play"),
            "blank_risk": cap.get("p_blank"),
            "ev_triple": round(2.0 * cap["ev"] + tc_gain, 2),
            "ev_normal": round(2.0 * cap["ev"], 2),
        }
        top = sorted(
            [{"name": r["web_name"], "extra_ev": r["ev"]} for r in line["xi"]],
            key=lambda r: -r["extra_ev"],
        )
        out["TC"]["alternatives"] = top[:5]

    # ---------------- Bench Boost ----------------
    if "BB" in (state["chips"].get("available_now") or []):
        total15 = float(P.sum(axis=1).mean())
        xi_ev = float(line["ev"])
        out["BB"] = {
            "gain": round(total15 - xi_ev, 2),
            "squad15_ev": round(total15, 2),
            "xi_ev_autosub": round(xi_ev, 2),
            "bench_ev": round(total15 - xi_ev, 2),
        }

    # ---------------- Free Hit ----------------
    # Best XI from the whole market within (bank + selling prices).
    if "FH" in (state["chips"].get("available_now") or []):
        budget = state["bank"] + sum(state["sell_prices"].values())
        vals0 = {}
        for pid, v in gw_projs.items():
            v0 = v[0] if v else 0.0
            vals0[int(pid)] = float(v0 or 0.0)
        try:
            fh_squad = planner.optimize_squad(df, budget, vals0)
        except Exception:
            fh_squad = None
        all_pos = {int(r["id"]): r.get("pos", "MID") for r in df.to_dict("records")}
        cur_xi = _xi_proj(squad_ids, vals0, pos_of)
        if fh_squad:
            fh_xi = _xi_proj(fh_squad, vals0, all_pos)
            out["FH"] = {
                "gain": round(fh_xi - cur_xi, 2),
                "best_xi_proj": round(fh_xi, 2),
                "current_xi_proj": round(cur_xi, 2),
                "budget": round(budget / 10.0, 1),
            }
        else:
            out["FH"] = {"gain": 0.0, "error": "optimizer tidak menemukan skuad"}

    # ---------------- Wildcard ----------------
    if "WC" in (state["chips"].get("available_now") or []):
        budget = state["bank"] + sum(state["sell_prices"].values())
        horizon_vals = {}
        for pid, vals in gw_projs.items():
            s = sum(float(v or 0.0) for v in (vals or [])[:horizon])
            horizon_vals[int(pid)] = s
        all_pos = {int(r["id"]): r.get("pos", "MID") for r in df.to_dict("records")}
        try:
            wc_squad = planner.optimize_squad(df, budget, horizon_vals)
        except Exception:
            wc_squad = None
        cur_total = sum(
            _xi_proj(squad_ids, {int(pid): float((vals or [0.0])[g] or 0.0) for pid, vals in gw_projs.items()}, pos_of)
            for g in range(horizon)
        )
        if wc_squad:
            best_total = sum(
                _xi_proj(wc_squad, {int(pid): float((vals or [0.0])[g] or 0.0) for pid, vals in gw_projs.items()}, all_pos)
                for g in range(horizon)
            )
            out["WC"] = {
                "gain": round(best_total - cur_total, 2),
                "best_total": round(best_total, 2),
                "current_total": round(cur_total, 2),
                "horizon": horizon,
                "budget": round(budget / 10.0, 1),
            }
        else:
            out["WC"] = {"gain": 0.0, "error": "optimizer tidak menemukan skuad"}

    # ---------------- Calendar status ----------------
    out["chips"] = state["chips"]
    out["bench_ev_detail"] = {
        "player_ev": [
            {"name": line["bench"][i]["web_name"], "ev": line["bench"][i]["ev"]}
            for i in range(len(line["bench"]))
        ]
    } if line.get("bench") else None
    return out
