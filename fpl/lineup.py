"""Manual lineup validation for the drag-and-drop pitch component.

The Team Builder still computes an automatic best XI. If the manager drags
players on the pitch, the resulting lineup must obey FPL formation rules and
be a permutation of the same 15-player squad.
"""

import math
from collections import Counter

POSITIONS = ("GK", "DEF", "MID", "FWD")
XI_SIZE = 11
BENCH_OUT_SIZE = 3
BENCH_GK_SIZE = 1
XI_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}


def _int_ids(values):
    out = []
    for value in values or []:
        try:
            pid = int(value)
        except (TypeError, ValueError):
            continue
        if pid not in out:
            out.append(pid)
    return out


def normalize_component_value(value):
    """Normalise the JS payload to Python lists/ints."""
    if not isinstance(value, dict):
        return None
    bench_gk = value.get("bench_gk")
    try:
        bench_gk = int(bench_gk) if bench_gk is not None else None
    except (TypeError, ValueError):
        bench_gk = None
    return {
        "xi": _int_ids(value.get("xi")),
        "bench_out": _int_ids(value.get("bench_out")),
        "bench_gk": bench_gk,
    }


def default_lineup(result):
    """Extract (xi, bench_out, bench_gk) from a best_xi() result."""
    if not result:
        return [], [], None
    xi = [int(p["id"]) for p in result.get("xi", [])]
    bench = result.get("bench", [])
    bench_out = [int(p["id"]) for p in bench if p.get("pos") != "GK"][:BENCH_OUT_SIZE]
    bench_gk = next((int(p["id"]) for p in bench if p.get("pos") == "GK"), None)
    return xi, bench_out, bench_gk


def validate_lineup(xi_ids, bench_out_ids, bench_gk_id, squad_by_id):
    """Validate a manual XI + bench against FPL rules.

    Returns a list of error strings. The lineup must contain exactly the same
    15 players as the squad, with 1 GK + 3..5 DEF + 2..5 MID + 1..3 FWD in
    the XI and 3 outfield substitutes plus 1 GK on the bench.
    """
    errors = []
    xi_ids = _int_ids(xi_ids)
    bench_out_ids = _int_ids(bench_out_ids)
    bench_gk_id = int(bench_gk_id) if bench_gk_id is not None else None

    if len(xi_ids) != XI_SIZE:
        errors.append(f"XI harus berisi {XI_SIZE} pemain")
    if len(bench_out_ids) != BENCH_OUT_SIZE:
        errors.append(f"Bench outfield harus berisi {BENCH_OUT_SIZE} pemain")
    if bench_gk_id is None:
        errors.append("Bench harus punya 1 kiper")

    all_ids = xi_ids + bench_out_ids + ([bench_gk_id] if bench_gk_id is not None else [])
    if len(all_ids) != len(set(all_ids)):
        errors.append("Ada pemain duplikat di lineup")
    if set(all_ids) != set(squad_by_id):
        errors.append("Lineup harus berisi tepat 15 pemain dari skuad")

    xi_players = [squad_by_id[pid] for pid in xi_ids if pid in squad_by_id]
    counts = Counter(p.get("pos", "MID") for p in xi_players)
    for pos in POSITIONS:
        if counts.get(pos, 0) < XI_MIN[pos] or counts.get(pos, 0) > XI_MAX[pos]:
            errors.append(
                f"Formasi XI tidak valid: {pos} {counts.get(pos, 0)} "
                f"(harus {XI_MIN[pos]}-{XI_MAX[pos]})"
            )
    if counts.get("GK", 0) != 1:
        errors.append("XI harus punya tepat 1 kiper")

    bench_gk = squad_by_id.get(bench_gk_id) if bench_gk_id is not None else None
    if bench_gk is not None and bench_gk.get("pos") != "GK":
        errors.append("Slot bench GK harus diisi kiper")
    for pid in bench_out_ids:
        player = squad_by_id.get(pid)
        if player is not None and player.get("pos") == "GK":
            errors.append("Kiper tidak boleh berada di bench outfield")

    return errors


def build_lineup_result(xi_ids, bench_out_ids, bench_gk_id, players_by_id):
    """Build a best_xi()-compatible result from a manual lineup."""
    xi = [players_by_id[pid] for pid in _int_ids(xi_ids) if pid in players_by_id]
    bench_out = [players_by_id[pid] for pid in _int_ids(bench_out_ids) if pid in players_by_id]
    bench_gk = players_by_id.get(int(bench_gk_id)) if bench_gk_id is not None else None
    bench = bench_out + ([bench_gk] if bench_gk else [])

    counts = Counter(p.get("pos", "MID") for p in xi)
    formation = (counts.get("DEF", 0), counts.get("MID", 0), counts.get("FWD", 0))
    ordered = sorted(xi, key=lambda p: float(p.get("proj") or 0), reverse=True)
    total = round(sum(float(p.get("proj") or 0) for p in xi), 2)

    return {
        "xi": xi,
        "bench": bench,
        "total": total,
        "formation": formation,
        "captain": ordered[0] if ordered else None,
        "vice": ordered[1] if len(ordered) > 1 else None,
    }


def _safe_float(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def compact_lineup_player(player, gw_cells):
    """Payload for the JS pitch component (JSON-safe)."""
    cells = []
    for cell in gw_cells or []:
        cells.append({
            "opp": str(cell.get("opp") or "-"),
            "ha": str(cell.get("ha") or ""),
            "fdr": int(cell.get("fdr") or 3),
            "pts": round(_safe_float(cell.get("pts")), 2),
        })
    return {
        "id": int(player["id"]),
        "name": str(player.get("web_name") or ""),
        "team": str(player.get("team_short") or ""),
        "pos": str(player.get("pos") or "MID"),
        "price": int(player.get("price") or 0),
        "proj": round(_safe_float(player.get("proj")), 2),
        "photo": str(player.get("photo_code") or ""),
        "status": str(player.get("status") or "a"),
        "gw": cells,
    }
