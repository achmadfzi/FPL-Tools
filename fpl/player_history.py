"""Per-player recent gameweek history (element-summary) cache.

The FPL bootstrap only exposes season *totals*. For a realistic Monte-Carlo
simulation (playing-minute expectations, rotation-risk signals, DefCon hit
probabilities, card/penalty rates) we need each player's recent per-GW data
(minutes, points, xG/xA, defensive actions). Data comes from the same
element-summary endpoint already used by paststats/reliability, cached per
player with a 7-day TTL (plus a "last recorded GW" check) so repeated
dashboard loads never re-fetch and recent form survives between GWs.

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

# Per-GW history only changes when a Gameweek finishes.  A 6-hour TTL made the
# whole recent-form layer silently disappear between GWs.  Keep data for a
# week, and additionally use the last recorded GW to decide whether a refresh
# is needed.
TTL = 7 * 24 * 3600
MAX_STALE = 30 * 24 * 3600


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
                "xgc": float(g.get("expected_goals_conceded") or 0),
                # DefCon: qualifying actions count for that match
                # (CBIT for DEF, CBIRT for MID/FWD as provided by the API).
                "dc": int(g.get("defensive_contribution") or 0),
                "saves": int(g.get("saves") or 0),
                "goals": int(g.get("goals_scored") or 0),
                "assists": int(g.get("assists") or 0),
                "cs": int(g.get("clean_sheets") or 0),
                "gc": int(g.get("goals_conceded") or 0),
                "bonus": int(g.get("bonus") or 0),
                "bps": int(g.get("bps") or 0),
                "threat": float(g.get("threat") or 0),
                "creativity": float(g.get("creativity") or 0),
                "influence": float(g.get("influence") or 0),
                "tackles": int(g.get("tackles") or 0),
                "cbi": int(g.get("clearances_blocks_interceptions") or 0),
                "recoveries": int(g.get("recoveries") or 0),
                "yc": int(g.get("yellow_cards") or 0),
                "rc": int(g.get("red_cards") or 0),
                "pen_missed": int(g.get("penalties_missed") or 0),
                "pen_saved": int(g.get("penalties_saved") or 0),
                "value": int(g.get("value") or 0),
                "selected": int(g.get("selected") or 0),
                "transfers_in": int(g.get("transfers_in") or 0),
                "transfers_out": int(g.get("transfers_out") or 0),
                "opponent": g.get("opponent_team"),
                "was_home": bool(g.get("was_home")),
            })
        return rows
    except Exception:
        return []


def _last_gw(rows):
    try:
        return max(int(r.get("gw") or 0) for r in rows)
    except (TypeError, ValueError):
        return 0


def _cache_status(entry, current_gw=None):
    """Classify a cached player-history entry.

    Returns one of: ``missing``, ``fresh``, ``stale_gw``, ``stale_age``,
    ``too_old``.  ``stale_gw`` / ``stale_age`` are still usable (better than
    dropping the entire recent-form layer), while ``too_old`` is ignored.
    """
    if not entry or not isinstance(entry.get("rows"), list) or not entry["rows"]:
        return "missing"
    age = time.time() - float(entry.get("ts", 0) or 0)
    if age > MAX_STALE:
        return "too_old"
    if current_gw is not None:
        last = _last_gw(entry["rows"])
        # Allow one blank/missing GW before declaring the cache stale.
        if last < int(current_gw) - 2:
            return "stale_gw" if age <= MAX_STALE else "too_old"
    if age > TTL:
        return "stale_age"
    return "fresh"


def _entry_rows(pid, current_gw=None, allow_stale=True):
    """Rows from the local file cache only (no network).

    Returns ``[]`` when missing/too old.  Stale-but-recent data is returned by
    default so the dashboard keeps its recent-form signal even if the user has
    not run a backfill for a few days.
    """
    data = _load_file()
    entry = data.get(str(pid))
    status = _cache_status(entry, current_gw=current_gw)
    if status in ("missing", "too_old"):
        return []
    if status != "fresh" and not allow_stale:
        return []
    return entry["rows"]


def cache_status(pid, current_gw=None):
    """Public helper for UI freshness badges."""
    return _cache_status(_load_file().get(str(pid)), current_gw=current_gw)


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


def _per90_from_rows(rows, field, last_n=6, min_minutes=45, min_row_minutes=20):
    """Recency-weighted per-90 rate for a per-match counting stat.

    Returns None when there is not enough data.  Very short cameos are
    excluded (a 5-minute appearance with one shot can imply an absurd
    70+/90 rate) and each match is weighted by minutes played, so a cameo
    cannot dominate the estimate.
    """
    played = [r for r in rows if r.get("minutes", 0) >= min_row_minutes][-last_n:]
    if not played:
        return None
    total_min = sum(r.get("minutes", 0) for r in played)
    if total_min < min_minutes:
        return None
    num, w, decay = 0.0, 0.0, 1.0
    for r in reversed(played):
        mins = min(float(r.get("minutes", 0)), 90.0)
        weight = decay * (mins / 90.0)
        num += float(r.get(field, 0)) * (90.0 / max(mins, 1.0)) * weight
        w += weight
        decay *= 0.75
    if w <= 0:
        return None
    return max(0.0, num / w)


def expected_minutes(pid, default=None, current_gw=None):
    """Expected minutes next GW for one player (may fetch; returns default on failure)."""
    try:
        pid = int(pid)
        rows = _entry_rows(pid, current_gw=current_gw)
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
             sleep_s=0.03, save_every=25, current_gw=None):
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
        if _cache_status(entry, current_gw=current_gw) == "fresh":
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


def backfill_if_stale(gd, ids=None, min_minutes=180, limit=None, progress=None):
    """Convenience wrapper: refresh only players whose cache is stale.

    Safe to call from a scheduled job after a Gameweek finishes.  It does not
    fetch anything when every selected player already has fresh data.
    """
    current_gw = None
    try:
        current_gw = int(gd.next_event["id"]) if gd is not None else None
    except Exception:
        current_gw = None
    return backfill(
        gd=gd,
        ids=ids,
        limit=limit,
        min_minutes=min_minutes,
        progress=progress,
        current_gw=current_gw,
    )


def exp_minutes_map(ids=None, current_gw=None, allow_stale=True):
    """{player_id: expected_minutes} from the file cache only (no network).

    Players without usable cached rows are omitted.  Recent-but-stale data is
    used by default (better than dropping the minutes signal entirely).
    """
    data = _load_file()
    out = {}
    targets = [int(i) for i in ids] if ids is not None else [int(k) for k in data.keys() if k.isdigit()]
    for pid in targets:
        entry = data.get(str(pid))
        status = _cache_status(entry, current_gw=current_gw)
        if status in ("missing", "too_old"):
            continue
        if status != "fresh" and not allow_stale:
            continue
        rows = entry["rows"]
        if len(rows) >= 2:
            em = _exp_minutes_from_rows(rows)
            if em is not None:
                out[pid] = round(em, 1)
    return out


def attach(gd, df, current_gw=None):
    """Attach history-derived columns to a projection DataFrame (file-cache only).

    Adds: hist_rows, hist_status, hist_last_gw, exp_minutes, rec_form,
    rec_xgi90, rec_xg90, rec_xa90, rec_dc90, rec_saves90, rec_yc90 and a
    handful of component rates (goals, assists, bonus, BPS, CS, threat,
    creativity).  The model/simulator can use these without any network call.
    """
    out = df.copy()
    if out is None or len(out) == 0:
        return out
    data = _load_file()
    if current_gw is None:
        try:
            current_gw = int(gd.next_event["id"])
        except Exception:
            current_gw = None

    hist_rows, hist_status, hist_last, exp_min = {}, {}, {}, {}
    rec_f, rec_x, rec_xg, rec_xa, rec_dc, rec_sv, rec_yc = {}, {}, {}, {}, {}, {}, {}
    rec_goals, rec_assists, rec_bonus, rec_bps, rec_cs, rec_gc = {}, {}, {}, {}, {}, {}
    rec_threat, rec_creativity = {}, {}

    for pid in out["id"].astype(int).tolist():
        entry = data.get(str(pid))
        status = _cache_status(entry, current_gw=current_gw)
        rows = []
        if status not in ("missing", "too_old"):
            rows = entry.get("rows") or []

        hist_rows[pid] = len(rows)
        hist_status[pid] = status
        hist_last[pid] = _last_gw(rows) if rows else None
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
        rec_goals[pid] = _per90_from_rows(rows, "goals")
        rec_assists[pid] = _per90_from_rows(rows, "assists")
        rec_bonus[pid] = _per90_from_rows(rows, "bonus")
        rec_bps[pid] = _per90_from_rows(rows, "bps")
        rec_cs[pid] = _per90_from_rows(rows, "cs")
        rec_gc[pid] = _per90_from_rows(rows, "gc")
        rec_threat[pid] = _per90_from_rows(rows, "threat")
        rec_creativity[pid] = _per90_from_rows(rows, "creativity")

    ids = out["id"].astype(int)
    out["hist_rows"] = ids.map(hist_rows)
    out["hist_status"] = ids.map(hist_status)
    out["hist_last_gw"] = ids.map(hist_last)
    out["exp_minutes"] = ids.map(exp_min)
    out["rec_form"] = ids.map(rec_f)
    out["rec_xgi90"] = ids.map(rec_x)
    out["rec_xg90"] = ids.map(rec_xg)
    out["rec_xa90"] = ids.map(rec_xa)
    out["rec_dc90"] = ids.map(rec_dc)
    out["rec_saves90"] = ids.map(rec_sv)
    out["rec_yc90"] = ids.map(rec_yc)
    out["rec_goals90"] = ids.map(rec_goals)
    out["rec_assists90"] = ids.map(rec_assists)
    out["rec_bonus90"] = ids.map(rec_bonus)
    out["rec_bps90"] = ids.map(rec_bps)
    out["rec_cs90"] = ids.map(rec_cs)
    out["rec_gc90"] = ids.map(rec_gc)
    out["rec_threat90"] = ids.map(rec_threat)
    out["rec_creativity90"] = ids.map(rec_creativity)
    return out
