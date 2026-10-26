"""Advanced transfer intelligence for FPL.

Multi-GW transfer planning, hit calculator, fixture ticker display,
and differential picks identification.
"""

from .availability import availability
from .utils import FDR_MULT


def multi_gw_value(player, gw_projs, horizon=3):
    """Calculate a player's total projected value over multiple GWs.

    Args:
        player: dict with player data
        gw_projs: dict {player_id: [proj_gw0, proj_gw1, ...]} from horizon module
        horizon: number of GWs to look ahead

    Returns: total projected points over the horizon
    """
    pid = player["id"]
    projs = gw_projs.get(pid, [0.0] * horizon)
    return round(sum(projs[:horizon]), 2)


def multi_gw_transfers(
    squad,
    pool,
    gw_projs,
    bank=0,
    horizon=3,
    sell_prices=None,
    club_max=3,
    min_in_chance=0.0,
) -> list[dict]:
    """Suggest transfers based on total gain over multiple GWs.

    Unlike the old suggest_transfers (1 GW only), this considers the total
    projected points over `horizon` GWs for both the current player and replacement.

    Budget is sell-price aware: each replacement must fit inside
    ``sell_price(current) + bank`` when `sell_prices` is given. The 3-players-
    per-club rule is enforced on the resulting squad.

    Availability is a hard filter for *incoming* players: injured, suspended
    or otherwise unavailable players (0% chance) are never suggested. Use
    ``min_in_chance`` to additionally require a minimum next-round chance
    (e.g. 75 to avoid doubtful players).

    Returns: sorted list of transfer candidates with multi-GW gain and
    availability data for both sides.
    """
    from collections import Counter

    squad_ids = {p["id"] for p in squad}
    club_counts = Counter(int(p["team"]) for p in squad)
    sell_prices = sell_prices or {}
    min_in_chance = float(min_in_chance or 0)

    # Pre-compute availability once per player (pool is ~700 rows).
    avail = {int(p["id"]): availability(p) for p in pool}
    for p in squad:
        avail.setdefault(int(p["id"]), availability(p))

    def _buyable(q):
        av = avail[int(q["id"])]
        return not av["is_out"] and av["pct"] >= min_in_chance

    by_pos = {
        pos: [
            p
            for p in pool
            if p["pos"] == pos and p.get("proj", 0) and p["proj"] > 0 and _buyable(p)
        ]
        for pos in ("GK", "DEF", "MID", "FWD")
    }

    candidates = []
    for p in squad:
        p_total = multi_gw_value(p, gw_projs, horizon)
        out_av = avail[int(p["id"])]
        out_sell = sell_prices.get(p["id"], p["price"])
        budget = out_sell + bank

        reps = []
        for q in by_pos.get(p["pos"], []):
            if q["id"] in squad_ids:
                continue
            if q["price"] > budget:
                continue
            # Club rule: replacing p with q must not create a 4th player from q's club
            q_club = int(q["team"])
            new_count = club_counts.get(q_club, 0) + (1 if q_club == int(p["team"]) else 0)
            if new_count > club_max:
                continue
            q_total = multi_gw_value(q, gw_projs, horizon)
            if q_total > p_total:
                q_av = avail[int(q["id"])]
                reps.append({
                    **q,
                    "gain_total": round(q_total - p_total, 2),
                    "proj_total": q_total,
                    "availability": q_av,
                    "availability_gain": round(q_av["pct"] - out_av["pct"], 1),
                })

        reps.sort(key=lambda q: q["gain_total"], reverse=True)
        top3 = reps[:3]
        if top3:
            candidates.append({
                "player": p,
                "player_total": p_total,
                "out_availability": out_av,
                "reps": top3,
                "gain": top3[0]["gain_total"],
                "gain_1gw": round(top3[0].get("proj", 0) - (p.get("proj") or 0), 2),
                "sell_price": out_sell,
            })

    candidates.sort(key=lambda c: c["gain"], reverse=True)
    return candidates


def injury_transfer_suggestions(
    squad,
    pool,
    gw_projs,
    bank=0,
    horizon=3,
    sell_prices=None,
    club_max=3,
    min_in_chance=0.0,
) -> list[dict]:
    """Combine injury/availability data with the best transfer replacement.

    Every squad player who is not fully available (injured, suspended,
    doubtful, or with a reduced chance of playing) appears once. The best
    affordable replacement is attached when one exists, together with the
    multi-GW gain and an action label:

    - ``JUAL SEKARANG`` for 0% chance,
    - ``PANTAU`` for 25-75% or doubtful,
    - ``TIDAK ADA OPSI`` when no better replacement fits the budget.

    Players who are fully available are omitted: injury is not a reason to
    sell them.
    """
    all_suggestions = multi_gw_transfers(
        squad,
        pool,
        gw_projs,
        bank=bank,
        horizon=horizon,
        sell_prices=sell_prices,
        club_max=club_max,
        min_in_chance=min_in_chance,
    )
    by_out = {int(s["player"]["id"]): s for s in all_suggestions}

    out = []
    for p in squad:
        av = availability(p)
        if av["status"] == "a" and av["pct"] >= 100:
            continue

        suggestion = by_out.get(int(p["id"]))
        rep = suggestion["reps"][0] if suggestion and suggestion.get("reps") else None
        rep_av = availability(rep) if rep else None
        gain = float(suggestion["gain"]) if suggestion else 0.0

        if rep:
            action = av["action"]
        else:
            action = "TIDAK ADA OPSI" if av["pct"] <= 0 else "PANTAU"

        out.append({
            "player": p,
            "availability": av,
            "replacement": rep,
            "replacement_availability": rep_av,
            "gain": round(gain, 2),
            "player_total": round(float(suggestion["player_total"]), 2) if suggestion else round(multi_gw_value(p, gw_projs, horizon), 2),
            "replacement_total": round(float(rep["proj_total"]), 2) if rep else None,
            "availability_gain": round(rep_av["pct"] - av["pct"], 1) if rep_av else None,
            "action": action,
        })

    out.sort(key=lambda s: (s["availability"]["severity"], s["gain"]), reverse=True)
    return out


def hit_calculator(current_player, replacement, gw_projs, horizon=3):
    """Calculate whether a -4 hit transfer is worth it.

    A hit is worth it if the total gain over the horizon exceeds 4 points.

    Returns: dict with gain breakdown and recommendation.
    """
    c_total = multi_gw_value(current_player, gw_projs, horizon)
    r_total = multi_gw_value(replacement, gw_projs, horizon)

    c_gw1 = gw_projs.get(current_player["id"], [0.0])[0]
    r_gw1 = gw_projs.get(replacement["id"], [0.0])[0]

    raw_gain = round(r_total - c_total, 2)
    net_gain = round(raw_gain - 4, 2)  # -4 hit penalty

    return {
        "current": current_player["web_name"],
        "replacement": replacement["web_name"],
        "gain_1gw": round(r_gw1 - c_gw1, 2),
        "gain_total": raw_gain,
        "net_after_hit": net_gain,
        "worth_hit": net_gain > 0,
        "horizon": horizon,
        "breakdown": {
            "current_total": c_total,
            "replacement_total": r_total,
            "hit_penalty": -4,
        },
    }


def fixture_ticker_table(gd, n_gws=6):
    """Build a fixture ticker table for display.

    Returns: list of dicts for table rendering:
        [{"team_id": X, "team_short": "ARS", "gw_N": "LIV (A) FDR 4", ...}]
    """
    ticker = gd.fixture_ticker(n_gws)
    cur = gd.next_event["id"]
    rows = []
    for team_id in sorted(gd.teams_by_id.keys()):
        team = gd.teams_by_id[team_id]
        row = {
            "team_id": team_id,
            "team_short": team["short_name"],
            "team_name": team.get("name", team["short_name"]),
        }
        team_fixtures = ticker.get(team_id, [])
        # Calculate average FDR for sorting (lower = easier run)
        fdrs = [f["fdr"] for f in team_fixtures]
        row["avg_fdr"] = round(sum(fdrs) / len(fdrs), 2) if fdrs else 3.0

        for gw_offset in range(n_gws):
            gw = cur + gw_offset
            gw_fxs = [f for f in team_fixtures if f["gw"] == gw]
            if not gw_fxs:
                row[f"gw_{gw}"] = {"text": "-", "fdr": None}
            elif len(gw_fxs) == 1:
                f = gw_fxs[0]
                ha = "K" if f["is_home"] else "T"
                row[f"gw_{gw}"] = {
                    "text": f"{f['opponent_short']} ({ha})",
                    "fdr": f["fdr"],
                    "is_home": f["is_home"],
                }
            else:
                # DGW
                parts = []
                fdr_min = 5
                for f in gw_fxs:
                    ha = "K" if f["is_home"] else "T"
                    parts.append(f"{f['opponent_short']}({ha})")
                    fdr_min = min(fdr_min, f["fdr"])
                row[f"gw_{gw}"] = {
                    "text": " & ".join(parts),
                    "fdr": fdr_min,
                    "dgw": True,
                }
        rows.append(row)

    rows.sort(key=lambda r: r["team_short"])
    return rows, cur


def differential_picks(players, ownership_threshold=5.0, min_proj=2.0, n=15):
    """Find differential picks: low ownership but high projected points.

    These are players that most managers don't have, giving you a unique
    advantage if they score well.

    Returns: list of players sorted by proj/ownership ratio.
    """
    diffs = []
    for p in players:
        if p.get("proj") is None or p["proj"] < min_proj:
            continue
        if p["selected_by"] >= ownership_threshold:
            continue
        if availability(p)["is_out"]:
            continue
        # Differential value = projection / sqrt(ownership + 0.1)
        # Lower ownership + higher projection = better differential
        diff_score = round(p["proj"] / max(p["selected_by"] + 0.1, 0.1) ** 0.5, 2)
        diffs.append({**p, "diff_score": diff_score})

    diffs.sort(key=lambda p: p["diff_score"], reverse=True)
    return diffs[:n]


def fixture_swing_badge(gw_projs, player_id, horizon=3, threshold=2.5):
    """Check if a player has a favorable fixture swing.

    Returns badge text if player's average per-GW projection is above threshold
    for upcoming GWs, None otherwise.
    """
    projs = gw_projs.get(player_id, [])
    future = projs[1:horizon] if len(projs) > 1 else []
    if not future:
        return None
    avg = sum(future) / len(future)
    if avg >= threshold:
        return f"SWING ↑ ({avg:.1f}/GW)"
    return None
