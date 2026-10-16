"""Per-player recent gameweek history (element-summary) cache.

The FPL bootstrap only exposes season *totals*. For a realistic Monte-Carlo
simulation (playing-minute expectations, rotation-risk signals, DefCon hit
probabilities, card/penalty rates) we need each player's recent per-GW data
(minutes, points, xG/xA, defensive actions). Data comes from the same
element-summary endpoint already used by paststats/reliability, cached per
player with a 6h TTL so repeated dashboard loads never re-fetch.

Guards:
- graceful degradation: if the network fails, expected minutes return None
- players with too little data return None (caller must handle)
- `attach()` is READ-ONLY (file cache only); only explicit helpers such as
  `expected_minutes()` / `backfill()` may trigger network fetches, and
  `backfill()` is rate-limited and reports progress.
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
                "xg": float(g.get("expected_goals") or 0),
                "xa": float(g.get("expected_assists") or 0),
                # DefCon: qualifying actions count for that match
                # (CBIT for DEF, CBIRT for MID/FWD as provided by the API).
                "dc": int(g.get("defensive_contribution") or 0),
                "saves": int(g.get("saves") or 0),
                "yc": int(g.get("yellow_cards") or 0),
                "rc": int(g.get("red_cards") or 0),
                "pen_missed": int(g.get("penalties_missed") or 0),
                "pen_saved": int(g.get("penalties_saved") or 0),
                "opponent": g.get("opponent_team"),
                "was_home": bool(g.get("was_home")),
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


def _per90_from_rows(rows, field, last_n=6, min_minutes=45):
    """Recency-weighted per-90 rate for a per-match counting stat.

    Returns None when there is not enough data. Non-playing rows are skipped.
    """
    played = [r for r in rows if r.get("minutes", 0) > 0][-last_n:]
    if not played:
        return None
    total_min = sum(r.get("minutes", 0) for r in played)
    if total_min < min_minutes:
        return None
    num, w, decay = 0.0, 0.0, 1.0
    for r in reversed(played):
        mins = r.get("minutes", 0)
        num += float(r.get(field, 0)) * (90.0 / max(mins, 1)) * decay
        w += decay
        decay *= 0.75
    if w <= 0:
        return None
    return max(0.0, num / w)


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


def backfill(gd=None, ids=None, limit=None, min_minutes=180, progress=None,
             sleep_s=0.03, save_every=25):
    """Fetch and cache element-summary rows for many players at once.

    Args:
        gd: GameData (uses gd.players to pick targets when ids is None)
        ids: explicit list of player ids (takes priority)
        limit: cap on how many players to fetch this run
        min_minutes: only players with at least this many season minutes
                     are selected when ids is None
        progress: optional callable(done, total, web_name)
        sleep_s: politeness delay between API calls

    Returns: dict {"fetched": n, "failed": n, "skipped": n, "total": n}
    """
    if ids is None:
        if gd is None:
            return {"fetched": 0, "failed": 0, "skipped": 0, "total": 0}
        pool = [p for p in gd.players if int(p.get("minutes") or 0) >= min_minutes]
        pool.sort(key=lambda p: (-(p.get("minutes") or 0), p["id"]))
        ids = [p["id"] for p in pool]
        names = {p["id"]: p.get("web_name", str(p["id"])) for p in pool}
    else:
        ids = [int(i) for i in ids]
        names = {}
        if gd is not None:
            names = {p["id"]: p.get("web_name", str(p["id"])) for p in gd.players}
    if limit is not None:
        ids = list(ids)[: int(limit)]

    data = _load_file()
    fetched = failed = skipped = 0
    total = len(ids)
    for i, pid in enumerate(ids, 1):
        entry = data.get(str(pid))
        fresh = entry and isinstance(entry.get("rows"), list) \
            and (time.time() - entry.get("ts", 0)) < TTL
        if fresh:
            skipped += 1
        else:
            rows = _rows_for(pid)
            if rows:
                data[str(pid)] = {"ts": time.time(), "rows": rows}
                fetched += 1
            else:
                failed += 1
            if sleep_s:
                time.sleep(sleep_s)
            if save_every and fetched % save_every == 0:
                _save_file(data)
        if progress is not None:
            progress(i, total, names.get(int(pid), str(pid)))
    _save_file(data)
    return {"fetched": fetched, "failed": failed, "skipped": skipped, "total": total}


def exp_minutes_map(ids=None):
    """{player_id: expected_minutes} from the file cache only (no network).

    Players without fresh cached rows are omitted from the map.
    """
    data = _load_file()
    now = time.time()
    out = {}
    targets = [int(i) for i in ids] if ids is not None else [int(k) for k in data.keys() if k.isdigit()]
    for pid in targets:
        entry = data.get(str(pid))
        if entry and isinstance(entry.get("rows"), list) and (now - entry.get("ts", 0)) < TTL:
            rows = entry["rows"]
            if len(rows) >= 2:
                em = _exp_minutes_from_rows(rows)
                if em is not None:
                    out[pid] = round(em, 1)
    return out


def attach(gd, df):
    """Attach history-derived columns to a projection DataFrame (file-cache only).

    Adds: hist_rows, exp_minutes, rec_form, rec_xgi90, rec_xg90, rec_xa90,
    rec_dc90, rec_saves90, rec_yc90.
    Players without fresh cache data get 0/None — no network calls happen here.
    Never raises.
    """
    out = df.copy()
    data = _load_file()
    now = time.time()
    hist_rows, exp_min = {}, {}
    rec_f, rec_x, rec_xg, rec_xa, rec_dc, rec_sv, rec_yc = {}, {}, {}, {}, {}, {}, {}

    def _cached_rows(pid):
        entry = data.get(str(pid))
        if entry and isinstance(entry.get("rows"), list) and (now - entry.get("ts", 0)) < TTL:
            return entry["rows"]
        return []

    for pid in out["id"].astype(int).tolist():
        rows = _cached_rows(pid)
        hist_rows[pid] = len(rows)
        exp_min[pid] = round(_exp_minutes_from_rows(rows), 1) if len(rows) >= 2 else None

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

        rec_xg[pid] = _per90_from_rows(rows, "xg")
        rec_xa[pid] = _per90_from_rows(rows, "xa")
        rec_dc[pid] = _per90_from_rows(rows, "dc")
        rec_sv[pid] = _per90_from_rows(rows, "saves")
        rec_yc[pid] = _per90_from_rows(rows, "yc")

    out["hist_rows"] = out["id"].astype(int).map(hist_rows)
    out["exp_minutes"] = out["id"].astype(int).map(exp_min)
    out["rec_form"] = out["id"].astype(int).map(rec_f)
    out["rec_xgi90"] = out["id"].astype(int).map(rec_x)
    out["rec_xg90"] = out["id"].astype(int).map(rec_xg)
    out["rec_xa90"] = out["id"].astype(int).map(rec_xa)
    out["rec_dc90"] = out["id"].astype(int).map(rec_dc)
    out["rec_saves90"] = out["id"].astype(int).map(rec_sv)
    out["rec_yc90"] = out["id"].astype(int).map(rec_yc)
    return out
