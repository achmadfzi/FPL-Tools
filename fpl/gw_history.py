"""Gameweek History & Points Timeline module.

Fetches and processes a manager's season history — rank progression,
points per GW, chip impact analysis, and optimal captain calculation.
"""

import json
import time
from pathlib import Path

from .api import (
    BASE_URL,
    DATA_DIR,
    _fetch_json,
    get_bootstrap,
    get_entry,
    get_entry_history,
    get_entry_picks,
)

HISTORY_CACHE = DATA_DIR / "gw_history_cache.json"
CACHE_TTL = 30 * 60  # 30 minutes


def _load_cache():
    if HISTORY_CACHE.exists():
        try:
            data = json.loads(HISTORY_CACHE.read_text())
            if time.time() - data.get("ts", 0) < CACHE_TTL:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _save_cache(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["ts"] = time.time()
    HISTORY_CACHE.write_text(json.dumps(data, indent=2))


def fetch_season_history(team_id):
    """Fetch full season history for a manager.

    Returns dict with:
        - gw_results: list of per-GW data (points, rank, transfers, etc.)
        - chips_played: list of chips used
        - overall: overall stats (total_points, overall_rank, etc.)
        - averages: dict {gw_id: average_points} from bootstrap events
    """
    cached = _load_cache()
    if cached and cached.get("team_id") == team_id:
        return cached

    try:
        hist = get_entry_history(team_id, force=True)
    except Exception as e:
        return {"error": str(e), "gw_results": [], "chips_played": []}

    current = hist.get("current", [])
    chips = hist.get("chips", [])

    # Get average points per GW from bootstrap
    averages = {}
    try:
        bootstrap = get_bootstrap()
        for ev in bootstrap.get("events", []):
            if ev.get("finished") or ev.get("data_checked"):
                averages[ev["id"]] = ev.get("average_entry_score", 0)
    except Exception:
        pass

    # Get entry info
    try:
        entry = get_entry(team_id)
    except Exception:
        entry = {}

    gw_results = []
    for gw in current:
        gw_id = gw.get("event")
        gw_results.append({
            "gw": gw_id,
            "points": gw.get("points", 0),
            "total_points": gw.get("total_points", 0),
            "overall_rank": gw.get("overall_rank", 0),
            "rank": gw.get("rank", 0),
            "bank": round(gw.get("bank", 0) / 10.0, 1),
            "team_value": round(gw.get("value", 1000) / 10.0, 1),
            "transfers_made": gw.get("event_transfers", 0),
            "transfers_cost": gw.get("event_transfers_cost", 0),
            "points_on_bench": gw.get("points_on_bench", 0),
            "average": averages.get(gw_id, 0),
        })

    # Compute stats
    if gw_results:
        points_list = [g["points"] for g in gw_results]
        best_gw = max(gw_results, key=lambda g: g["points"])
        worst_gw = min(gw_results, key=lambda g: g["points"])
        total_hits = sum(g["transfers_cost"] for g in gw_results)
        total_bench_pts = sum(g["points_on_bench"] for g in gw_results)
        avg_points = round(sum(points_list) / len(points_list), 1)
    else:
        best_gw = worst_gw = None
        total_hits = total_bench_pts = 0
        avg_points = 0

    result = {
        "team_id": team_id,
        "team_name": entry.get("name", "FPL Team"),
        "manager_name": f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip(),
        "overall_points": entry.get("summary_overall_points", 0),
        "overall_rank": entry.get("summary_overall_rank", 0),
        "gw_results": gw_results,
        "chips_played": chips,
        "best_gw": best_gw,
        "worst_gw": worst_gw,
        "total_hits": total_hits,
        "total_bench_pts": total_bench_pts,
        "avg_points_per_gw": avg_points,
        "averages": averages,
    }

    _save_cache(result)
    return result


def chip_impact(history_data):
    """Analyze the impact of each chip used.

    For each chip played, find the GW points and compare with the manager's
    average to estimate the chip's incremental value.

    Returns: list of {chip, gw, points, avg, gain}
    """
    chips = history_data.get("chips_played", [])
    gw_map = {g["gw"]: g for g in history_data.get("gw_results", [])}
    avg_pts = history_data.get("avg_points_per_gw", 0)

    chip_labels = {
        "bboost": "Bench Boost",
        "3xc": "Triple Captain",
        "wildcard": "Wildcard",
        "freehit": "Free Hit",
    }

    results = []
    for c in chips:
        gw_id = c.get("event")
        chip_name = c.get("name", "unknown")
        gw_data = gw_map.get(gw_id)
        if gw_data:
            points = gw_data["points"]
            gain = round(points - avg_pts, 1) if avg_pts else 0
            results.append({
                "chip": chip_labels.get(chip_name, chip_name),
                "chip_key": chip_name,
                "gw": gw_id,
                "points": points,
                "avg": avg_pts,
                "gain": gain,
                "bench_pts": gw_data.get("points_on_bench", 0),
            })

    return results


def optimal_captain_calc(team_id, n_gws=None):
    """Calculate how many points the manager would have with optimal captains.

    For each completed GW, fetch the picks and live data, find which player
    in the squad scored the most, and compare with the actual captain choice.

    Returns: dict with total_actual, total_optimal, captain_details per GW.

    Note: This is expensive (1 API call per GW), so it's cached.
    """
    try:
        hist = get_entry_history(team_id)
        completed_gws = hist.get("current", [])
    except Exception:
        return {"error": "Gagal mengambil history", "details": []}

    if n_gws:
        completed_gws = completed_gws[:n_gws]

    details = []
    total_actual_captain_pts = 0
    total_optimal_captain_pts = 0

    for gw_data in completed_gws:
        gw_id = gw_data["event"]

        # Fetch picks for this GW
        try:
            picks_data = get_entry_picks(team_id, gw_id)
            picks = picks_data.get("picks", [])
        except Exception:
            continue

        # Fetch live data for this GW
        try:
            live = _fetch_json(f"{BASE_URL}/event/{gw_id}/live/", ttl=3600)
            live_map = {e["id"]: e["stats"]["total_points"]
                        for e in live.get("elements", [])}
        except Exception:
            continue

        # Find actual captain and their points
        captain_id = next((p["element"] for p in picks if p.get("is_captain")), None)
        captain_mult = next((p["multiplier"] for p in picks if p.get("is_captain")), 2)

        if captain_id is None:
            continue

        captain_pts = live_map.get(captain_id, 0)
        actual_captain_bonus = captain_pts * (captain_mult - 1)

        # Find optimal captain (highest scoring player in squad)
        squad_ids = [p["element"] for p in picks]
        squad_scores = [(pid, live_map.get(pid, 0)) for pid in squad_ids]
        optimal = max(squad_scores, key=lambda x: x[1])
        optimal_id, optimal_pts = optimal
        optimal_captain_bonus = optimal_pts * (captain_mult - 1)

        total_actual_captain_pts += actual_captain_bonus
        total_optimal_captain_pts += optimal_captain_bonus

        # Get player names from bootstrap
        try:
            bootstrap = get_bootstrap()
            elem_map = {e["id"]: e["web_name"] for e in bootstrap.get("elements", [])}
        except Exception:
            elem_map = {}

        details.append({
            "gw": gw_id,
            "captain_id": captain_id,
            "captain_name": elem_map.get(captain_id, f"ID {captain_id}"),
            "captain_pts": captain_pts,
            "captain_bonus": actual_captain_bonus,
            "optimal_id": optimal_id,
            "optimal_name": elem_map.get(optimal_id, f"ID {optimal_id}"),
            "optimal_pts": optimal_pts,
            "optimal_bonus": optimal_captain_bonus,
            "was_optimal": captain_id == optimal_id,
            "missed_pts": optimal_captain_bonus - actual_captain_bonus,
        })

    return {
        "total_actual_captain_pts": total_actual_captain_pts,
        "total_optimal_captain_pts": total_optimal_captain_pts,
        "missed_total": total_optimal_captain_pts - total_actual_captain_pts,
        "optimal_rate": round(
            sum(1 for d in details if d["was_optimal"]) / max(len(details), 1) * 100, 1
        ),
        "details": details,
    }
