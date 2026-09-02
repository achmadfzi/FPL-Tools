"""Per-player recent gameweek history (element-summary) cache.

The FPL bootstrap only exposes season *totals*. For a realistic Monte-Carlo
simulation (playing-minute expectations, rotation-risk signals) we need each
player's recent per-GW minutes/points/xG. Data comes from the same
element-summary endpoint already used by paststats/reliability, cached per
player with a 6h TTL so repeated dashboard loads never re-fetch.

Guards:
- graceful degradation: if the network fails, expected minutes return None
- players with too little data return None (caller must handle)
- `attach()` is READ-ONLY (file cache only); only explicit helpers such as
  `expected_minutes()` / `recency_features()` may trigger a network fetch,
  and only for a single player id at a time.
"""

import json
import time
from pathlib import Path

from .api import DATA_DIR, get_element_summary

FILE = DATA_DIR / "player_history.json"
TTL = 6 * 3600


def _load_file():
    if FILE.exists():
        try:
            return json.loads(FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_file(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data))


def _rows_for(pid):
    """Return per-GW history rows for a player straight from the API."""
    try:
        summary = get_element_summary(pid)
        hist = summary.get("history") or []
        rows = []
        for g in hist:
            minutes = int(g.get("minutes") or 0)
            rows.append({
                "gw": g.get("round"),
                "minutes": minutes,
                "starts": int(g.get("starts") or 0),
                "points": int(g.get("total_points") or 0),
                "xgi": float(g.get("expected_goal_involvements") or 0),
            })
        return rows
    except Exception:
        return []


def _entry_rows(pid):
    """Rows from the local file cache only (no network). [] if stale/missing."""
    data = _load_file()
    entry = data.get(str(pid))
    if entry and isinstance(entry.get("rows"), list) \
            and (time.time() - entry.get("ts", 0)) < TTL:
        return entry["rows"]
    return []


def _exp_minutes_from_rows(rows):
    """Weighted recent minutes expectation (per future match), 0..90 or None."""
    rows = [r for r in rows if r.get("minutes", 0) > 0][-6:]
    if not rows:
        return None
    num, w, decay = 0.0, 0.0, 1.0
    for r in reversed(rows):
        num += float(r.get("minutes", 0)) * decay
        w += decay
        decay *= 0.65
    if w <= 0:
        return None
    return min(90.0, max(0.0, num / w))


def expected_minutes(pid, default=None):
    """Expected minutes next GW for one player (may fetch; returns default on failure)."""
    try:
        pid = int(pid)
        rows = _entry_rows(pid)
        if not rows:
            rows = _rows_for(pid)
            if rows:
                data = _load_file()
                data[str(pid)] = {"ts": time.time(), "rows": rows}
                _save_file(data)
        if len(rows) < 2:
            return default
        return _exp_minutes_from_rows(rows)
    except Exception:
        return default


def attach(gd, df):
    """Attach history-derived columns to a projection DataFrame (file-cache only).

    Adds: hist_rows, exp_minutes, rec_form, rec_xgi90.
    Players without fresh cache data get 0/None — no network calls happen here.
    Never raises.
    """
    out = df.copy()
    data = _load_file()
    hist_rows, exp_min, rec_f, rec_x = {}, {}, {}, {}
    for pid in out["id"].astype(int).tolist():
        rows = []
        entry = data.get(str(pid))
        if entry and isinstance(entry.get("rows"), list) \
                and (time.time() - entry.get("ts", 0)) < TTL:
            rows = entry["rows"]
        hist_rows[pid] = len(rows)
        if len(rows) >= 2:
            exp_min[pid] = round(_exp_minutes_from_rows(rows), 1) if rows else None
        else:
            exp_min[pid] = None
        played = [r for r in rows if r.get("minutes", 0) >= 45][-5:]
        if len(rows) >= 3 and played:
            decay = 1.0
            w_pts, num_pts = 0.0, 0.0
            w_xgi, num_xgi = 0.0, 0.0
            for r in reversed(played):
                num_pts += float(r.get("points", 0)) * decay
                w_pts += decay
                if r.get("minutes", 0) >= 60:
                    per90 = (float(r.get("xgi", 0)) * 90.0) / max(r.get("minutes", 90), 1)
                    num_xgi += per90 * decay
                    w_xgi += decay
                decay *= 0.7
            rec_f[pid] = round(num_pts / w_pts, 2) if w_pts else None
            rec_x[pid] = round(num_xgi / w_xgi, 3) if w_xgi else None
        else:
            rec_f[pid] = None
            rec_x[pid] = None

    out["hist_rows"] = out["id"].astype(int).map(hist_rows)
    out["exp_minutes"] = out["id"].astype(int).map(exp_min)
    out["rec_form"] = out["id"].astype(int).map(rec_f)
    out["rec_xgi90"] = out["id"].astype(int).map(rec_x)
    return out
