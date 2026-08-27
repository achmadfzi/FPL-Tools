"""FPL Team integration & sync module.

Fetches manager profile, squad picks, chips, and transfer history from FPL API
using the public FPL Team ID (Entry ID).
"""

import json
import time
from pathlib import Path

from .api import DATA_DIR, get_bootstrap, get_entry, get_entry_history, get_entry_picks

MANAGER_FILE = DATA_DIR / "manager.json"
SQUAD_FILE = DATA_DIR / "squad.json"


def load_manager():
    """Load saved manager profile if available."""
    if MANAGER_FILE.exists():
        try:
            return json.loads(MANAGER_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_manager(data):
    """Save manager profile to data/manager.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANAGER_FILE.write_text(json.dumps(data, indent=2))


def get_saved_team_id():
    """Get the currently saved FPL Team ID."""
    mgr = load_manager()
    if mgr and "team_id" in mgr:
        return mgr["team_id"]
    return None


def get_latest_completed_or_current_gw():
    """Determine the latest gameweek that has picks available."""
    try:
        bootstrap = get_bootstrap()
        events = bootstrap.get("events", [])
        # Look for current event first, then last finished, or event 1
        current = next((e for e in events if e.get("is_current")), None)
        if current:
            return current["id"]
        finished = [e for e in events if e.get("finished")]
        if finished:
            return finished[-1]["id"]
        return 1
    except Exception:
        return 1


def sync_team(team_id, gw_id=None, force=True):
    """Sync FPL team info and squad picks using FPL Team ID.

    Saves picks to data/squad.json and full profile to data/manager.json.
    Returns (success: bool, data: dict, error: str).
    """
    try:
        team_id = int(str(team_id).strip())
    except (ValueError, TypeError):
        return False, None, "ID Tim FPL harus berupa angka (contoh: 925693)."

    try:
        entry = get_entry(team_id, force=force)
    except Exception as e:
        return False, None, f"Gagal mengambil profil tim FPL (ID: {team_id}): {e}"

    if not entry or "id" not in entry:
        return False, None, f"Tim dengan ID {team_id} tidak ditemukan di FPL."

    if gw_id is None:
        gw_id = get_latest_completed_or_current_gw()

    # Try fetching picks for target GW, fallback to GW-1 or GW 1
    picks_data = None
    used_gw = gw_id
    for test_gw in [gw_id, gw_id - 1, 1]:
        if test_gw < 1:
            continue
        try:
            res = get_entry_picks(team_id, test_gw, force=force)
            if res and "picks" in res and len(res["picks"]) == 15:
                picks_data = res
                used_gw = test_gw
                break
        except Exception:
            continue

    if not picks_data or "picks" not in picks_data:
        return False, None, f"Belum ada data susunan pemain (picks) untuk tim ID {team_id}."

    picks = picks_data["picks"]
    squad_ids = [p["element"] for p in picks]
    starters = [p["element"] for p in picks if p.get("multiplier", 1) > 0 or p.get("position", 1) <= 11]
    bench = [p["element"] for p in picks if p.get("position", 1) > 11]
    captain = next((p["element"] for p in picks if p.get("is_captain")), None)
    vice_captain = next((p["element"] for p in picks if p.get("is_vice_captain")), None)

    # Entry history / Chips
    entry_hist = picks_data.get("entry_history", {})
    active_chip = picks_data.get("active_chip")

    # Fetch season history & chips played
    chips_played = []
    try:
        hist = get_entry_history(team_id, force=force)
        chips_played = hist.get("chips", [])
    except Exception:
        pass

    manager_data = {
        "team_id": team_id,
        "team_name": entry.get("name", "FPL Team"),
        "manager_name": f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip(),
        "summary_overall_points": entry.get("summary_overall_points", 0),
        "summary_overall_rank": entry.get("summary_overall_rank", 0),
        "summary_event_points": entry.get("summary_event_points", 0),
        "bank": entry_hist.get("bank", 0) / 10.0 if "bank" in entry_hist else 0.0,
        "team_value": entry_hist.get("value", 1000) / 10.0 if "value" in entry_hist else 100.0,
        "gw_synced": used_gw,
        "active_chip": active_chip,
        "chips_played": chips_played,
        "squad_ids": squad_ids,
        "starters": starters,
        "bench": bench,
        "captain_id": captain,
        "vice_captain_id": vice_captain,
        "synced_at": time.time(),
    }

    # Save to data/manager.json
    save_manager(manager_data)

    # Save to data/squad.json
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SQUAD_FILE.write_text(json.dumps(squad_ids))
    except Exception:
        pass

    return True, manager_data, None
