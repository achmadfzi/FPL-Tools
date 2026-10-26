"""Validation and data helpers for the drag-and-drop squad builder.

The JavaScript component is only the presentation layer. These helpers are
the single source of truth for FPL squad legality, so a malformed or
out-of-date frontend can never save an illegal squad.
"""

import math
from collections import Counter

POSITIONS = ("GK", "DEF", "MID", "FWD")
SQUAD_NEED = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
DEFAULT_BUDGET = 1000  # tenths of a million -> £100.0m
DEFAULT_CLUB_MAX = 3
DEFAULT_SQUAD_SIZE = 15


def empty_selected():
    return {pos: [] for pos in POSITIONS}


def normalize_selected(value):
    """Normalise a component value to {pos: [int, ...]}.

    Unknown positions and malformed IDs are ignored; duplicates within one
    position are removed while preserving order.
    """
    out = empty_selected()
    if not isinstance(value, dict):
        return out
    for pos in POSITIONS:
        raw = value.get(pos) or []
        if isinstance(raw, (str, int)):
            raw = [raw]
        try:
            iterator = list(raw)
        except TypeError:
            continue
        for item in iterator:
            try:
                pid = int(item)
            except (TypeError, ValueError):
                continue
            if pid not in out[pos]:
                out[pos].append(pid)
    return out


def group_player_ids(ids, players_by_id):
    """Group a flat list of player IDs by their real FPL position."""
    out = empty_selected()
    for raw in ids or []:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        player = players_by_id.get(pid)
        if player and pid not in out[player["pos"]]:
            out[player["pos"]].append(pid)
    return out


def selected_ids(selected):
    """Flat ID list in GK/DEF/MID/FWD order."""
    return [pid for pos in POSITIONS for pid in selected.get(pos, [])]


def _safe_float(value, default=0.0):
    """Float that is JSON-safe (NaN/Infinity become the default)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _safe_chance(value):
    """Chance as 0-100 or None; NaN is not valid JSON."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def compact_player(player):
    """Minimal player payload the JavaScript component needs to render."""
    chance = player.get("chance_next", player.get("chance"))
    return {
        "id": int(player["id"]),
        "name": str(player.get("web_name") or ""),
        "team": str(player.get("team_short") or ""),
        "pos": str(player.get("pos") or "MID"),
        "price": int(player.get("price") or 0),
        "proj": round(_safe_float(player.get("proj")), 2),
        "photo": str(player.get("photo_code") or ""),
        "status": str(player.get("status") or "a"),
        "chance": _safe_chance(chance),
    }


def selection_stats(selected, players_by_id, budget=DEFAULT_BUDGET):
    """Return count/cost/bank/club usage for a selection."""
    ids = selected_ids(selected)
    players = [players_by_id[pid] for pid in ids if pid in players_by_id]
    cost = sum(int(p.get("price") or 0) for p in players)
    clubs = Counter(int(p.get("team") or 0) for p in players)
    return {
        "count": len(players),
        "cost": cost,
        "budget": int(budget),
        "bank": int(budget) - cost,
        "clubs": dict(clubs),
        "max_club": max(clubs.values(), default=0),
    }


def validate_selection(
    selected,
    players_by_id,
    budget=DEFAULT_BUDGET,
    club_max=DEFAULT_CLUB_MAX,
    squad_size=DEFAULT_SQUAD_SIZE,
):
    """Validate a squad selection; returns a list of error strings.

    A partial squad is allowed (the user is still dragging players in), but
    it may never exceed the position quotas, the total size, the club limit,
    or the budget.
    """
    errors = []
    seen = set()
    ids = selected_ids(selected)
    stats = selection_stats(selected, players_by_id, budget)

    for pos in POSITIONS:
        pos_ids = selected.get(pos, [])
        if len(pos_ids) > SQUAD_NEED[pos]:
            errors.append(f"Posisi {pos} maksimal {SQUAD_NEED[pos]} pemain")
        for pid in pos_ids:
            player = players_by_id.get(pid)
            if player is None:
                errors.append(f"Pemain ID {pid} tidak ditemukan")
                continue
            if pid in seen:
                errors.append(f"Pemain {player.get('web_name', pid)} duplikat")
            seen.add(pid)
            if player.get("pos") != pos:
                errors.append(
                    f"{player.get('web_name', pid)} adalah {player.get('pos')}, bukan {pos}"
                )

    if len(ids) > squad_size:
        errors.append(f"Skuad maksimal {squad_size} pemain")
    if stats["cost"] > int(budget):
        errors.append(
            f"Budget terlampaui: £{stats['cost'] / 10:.1f}m > £{int(budget) / 10:.1f}m"
        )
    if stats["max_club"] > club_max:
        errors.append(f"Maksimal {club_max} pemain per klub")

    return errors
