"""Historical accuracy tracking for FPL projections.

Saves projections before each GW, fetches actuals after GW finishes,
computes accuracy metrics, and suggests weight adjustments.
"""

import json
import math
import time
from pathlib import Path

from . import snapshots
from .api import DATA_DIR, get_bootstrap, get_fixtures

FILE = DATA_DIR / "accuracy.json"


def _load():
    if FILE.exists():
        try:
            return json.loads(FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data, indent=2))


def _gw_deadline(gw_id):
    """Deadline ISO string for a Gameweek, or None when unavailable."""
    try:
        bootstrap = get_bootstrap()
        for event in bootstrap.get("events", []):
            if int(event.get("id", -1)) == int(gw_id):
                return event.get("deadline_time")
    except Exception:
        pass
    return None


def _deadline_ts(deadline_iso):
    if not deadline_iso:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(deadline_iso).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def save_projections(gw_id, df, force=False):
    """Save projections for a GW, keeping the latest pre-deadline state.

    Historically this function saved only the first snapshot of a Gameweek.
    That meant a dashboard opened on Monday (before late team news) was used
    for accuracy evaluation even when the user refreshed on Friday.  We now:

    * write a timestamped snapshot on every (throttled) call;
    * keep ``accuracy.json`` pointed at the latest pre-deadline projection;
    * refuse to overwrite after the deadline unless ``force=True``.

    Stores the *raw* projection ("proj") for model training plus the served
    value ("proj_served") and a full feature snapshot so the adaptive,
    calibration and ML layers can be re-fitted without look-ahead.
    """
    data = _load()
    key = f"gw_{gw_id}"
    deadline = _gw_deadline(gw_id)
    deadline_ts = _deadline_ts(deadline)
    after_deadline = deadline_ts is not None and time.time() > deadline_ts

    # Timestamped snapshot (cheap, throttled inside snapshots.py).
    snapshot_path = None
    try:
        snapshot_path = snapshots.save_projection_snapshot(
            int(gw_id), df, deadline=deadline, force=force
        )
    except Exception:
        snapshot_path = None

    if key in data and "projections" in data.get(key, {}) and after_deadline and not force:
        # Deadline has passed: keep the last pre-deadline state.
        return False

    feature_cols = [
        ("own", "own"),
        ("own_total", "own_total"),
        ("ep_next_fpl", "ep_next"),
        ("fixture_mult", "fixture_mult"),
        ("dyn_mult", "dyn_mult"),
        ("home_mult", "home_mult"),
        ("cs_prob", "cs_prob"),
        ("threat_norm", "threat"),
        ("xgi_signal", "xgi_sig"),
        ("ict_signal", "ict_sig"),
        ("bonus_norm", "bonus"),
        ("creativity_norm", "creativity"),
        ("dc_prob", "dc_prob"),
        ("dc_bonus", "dc_bonus"),
        ("dc_lam90", "dc_lam90"),
        ("dc_n", "dc_n"),
        ("dc_method", "dc_method"),
        ("minutes_factor", "minutes_factor"),
        ("exp_minutes", "exp_minutes"),
        ("hist_rows", "hist_rows"),
        ("form", "form"),
        ("ppg", "ppg"),
        ("rec_form", "rec_form"),
        ("xGI_per90", "xgi90"),
        ("rec_xgi90", "rec_xgi90"),
        ("xG_per90", "xg_per90"),
        ("rec_xg90", "rec_xg90"),
        ("xA_per90", "xa_per90"),
        ("rec_xa90", "rec_xa90"),
        ("rec_dc90", "rec_dc90"),
        ("rec_saves90", "rec_saves90"),
        ("saves_per_game", "saves_per_game"),
        ("selected_by", "selected_by"),
        ("minutes", "minutes"),
        ("starts", "starts"),
        ("price", "price"),
        ("chance", "chance"),
        ("status", "status"),
        ("news", "news"),
        ("pen_order", "pen_order"),
    ]

    def _num(v):
        try:
            f = float(v)
            if math.isnan(f):
                return None
            return round(f, 4)
        except (TypeError, ValueError):
            return None

    def _text(v):
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        text = str(v).strip()
        return text or None

    projections = {}
    for _, row in df.iterrows():
        proj = row.get("proj")
        if proj is None or (isinstance(proj, float) and math.isnan(proj)):
            continue
        raw = row.get("proj_pre_cal")
        raw = float(raw) if raw is not None and not (isinstance(raw, float) and math.isnan(raw)) else float(proj)
        entry = {
            "proj": round(raw, 2),
            "proj_served": _num(proj),
            "pos": row.get("pos", "MID"),
            "fdr": int(row["fdr"]) if row.get("fdr") is not None and not (isinstance(row.get("fdr"), float) and math.isnan(row.get("fdr"))) else None,
            "web_name": row.get("web_name", ""),
            "team_short": row.get("team_short", ""),
            "is_home": bool(row.get("is_home")) if row.get("is_home") is not None else None,
            "n_fixtures": int(row.get("n_fixtures") or 1),
            "status": _text(row.get("status")),
            "news": _text(row.get("news")),
            "chance": _num(row.get("chance")),
        }
        for src, dst in feature_cols:
            if src in df.columns:
                entry[dst] = _num(row.get(src))
        projections[str(int(row["id"]))] = entry

    data[key] = {
        "saved_at": time.time(),
        "deadline": deadline,
        "snapshot_path": str(snapshot_path) if snapshot_path else None,
        "projections": projections,
    }
    _save(data)
    return True


def is_gw_finished(gw_id):
    """Check if a gameweek is finished, either marked in events or all fixtures completed."""
    try:
        bootstrap = get_bootstrap()
    except Exception:
        return False

    events = bootstrap.get("events", [])
    gw_event = None
    for e in events:
        if e["id"] == gw_id:
            gw_event = e
            break

    if gw_event is None:
        return False

    if gw_event.get("finished"):
        return True

    # Check fixtures: if all fixtures for this GW are finished or finished_provisional
    try:
        fixtures = get_fixtures()
        gw_fixtures = [f for f in fixtures if f.get("event") == gw_id]
        if gw_fixtures and all(f.get("finished") or f.get("finished_provisional") for f in gw_fixtures):
            return True
    except Exception:
        pass

    return False


def fetch_actuals(gw_id):
    """Fetch actual scores for a completed GW from the FPL API.

    Returns dict {player_id_str: actual_points} or None if GW not finished.
    """
    if not is_gw_finished(gw_id):
        return None

    # Player points for this GW come from the bootstrap's elements
    # but we need per-GW data — use the live endpoint or reconstruct from history
    # For simplicity, use total_points difference or the history endpoint
    # The FPL API has a live endpoint: /api/event/{id}/live/
    try:
        from .api import _fetch_json, BASE_URL
        live = _fetch_json(f"{BASE_URL}/event/{gw_id}/live/", ttl=3600)
        actuals = {}
        for elem in live.get("elements", []):
            pid = str(elem["id"])
            stats = elem.get("stats", {})
            actuals[pid] = int(stats.get("total_points", 0))
        return actuals
    except Exception:
        return None


_ACTUAL_STAT_KEYS = (
    "minutes",
    "total_points",
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "bonus",
    "bps",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
    "defensive_contribution",
    "saves",
    "yellow_cards",
    "red_cards",
    "penalties_saved",
    "penalties_missed",
    "value",
    "selected",
    "transfers_in",
    "transfers_out",
)


def fetch_actual_stats(gw_id):
    """Fetch per-player actual stat lines for a completed GW.

    Stores the component events (minutes, goals, assists, CS, bonus, BPS,
    DefCon, saves, cards) so future calibration can ask *which* component is
    wrong instead of only looking at total points.
    """
    if not is_gw_finished(gw_id):
        return None
    try:
        from .api import BASE_URL, _fetch_json

        live = _fetch_json(f"{BASE_URL}/event/{gw_id}/live/", ttl=3600)
        out = {}
        for elem in live.get("elements", []):
            stats = elem.get("stats", {}) or {}
            out[str(elem["id"])] = {
                key: stats.get(key) for key in _ACTUAL_STAT_KEYS if key in stats
            }
        return out
    except Exception:
        return None


def _price_bucket(price):
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p <= 45:
        return "<=4.5m"
    if p <= 60:
        return "4.6-6.0m"
    if p <= 80:
        return "6.1-8.0m"
    if p <= 110:
        return "8.1-11.0m"
    return ">11.0m"


def _ownership_bucket(selected):
    try:
        s = float(selected)
    except (TypeError, ValueError):
        return None
    if s < 1:
        return "<1%"
    if s < 5:
        return "1-5%"
    if s < 15:
        return "5-15%"
    if s < 30:
        return "15-30%"
    return ">=30%"


def _spearman(xs, ys):
    """Spearman rank correlation without scipy (safe on tiny samples)."""
    n = len(xs)
    if n < 3:
        return None

    def _ranks(values):
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks

    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return round(num / den, 4) if den else None


def _group_errors(errors, key_fn):
    groups = {}
    for e in errors:
        key = key_fn(e)
        if key is None:
            continue
        groups.setdefault(str(key), []).append(e)
    out = {}
    for key, rows in groups.items():
        out[key] = {
            "n": len(rows),
            "mae": round(sum(abs(r["error"]) for r in rows) / len(rows), 3),
            "bias": round(sum(r["error"] for r in rows) / len(rows), 3),
        }
    return out


def compute_accuracy(gw_id):
    """Compute accuracy metrics for a completed GW.

    Besides MAE/RMSE this stores decision-relevant diagnostics:

    * bias (signed error) overall and by position/FDR/price/ownership;
    * top-K error (the players that actually enter captain/transfer choices);
    * decile calibration (is the top end over/under-predicted?);
    * Spearman rank correlation;
    * a simple captain regret proxy (top projection vs the best actual in
      the projected pool).
    """
    data = _load()
    key = f"gw_{gw_id}"
    if key not in data or "projections" not in data[key]:
        return None

    entry = data[key]

    # Fetch actuals if not already stored
    if "actuals" not in entry:
        actuals = fetch_actuals(gw_id)
        if actuals is None:
            return None
        entry["actuals"] = actuals
        _save(data)
    else:
        actuals = entry["actuals"]

    # Full component stats (best effort; old accuracy files keep working).
    if "actual_stats" not in entry:
        try:
            stats = fetch_actual_stats(gw_id)
            if stats:
                entry["actual_stats"] = stats
                _save(data)
        except Exception:
            pass

    projections = entry["projections"]
    # Prefer the last timestamped snapshot taken before the deadline.  This is
    # more robust than relying only on accuracy.json being refreshed by a
    # browser tab.
    try:
        snap = snapshots.pre_deadline_snapshot(gw_id, entry.get("deadline"))
        if snap and float(snap.get("saved_at") or 0) > float(entry.get("saved_at") or 0):
            snap_projs = snapshots.snapshot_projections(snap)
            if snap_projs:
                projections = snap_projs
    except Exception:
        pass
    actual_stats = entry.get("actual_stats") or {}

    errors = []
    by_pos = {}
    by_fdr = {}

    for pid, proj_info in projections.items():
        if pid not in actuals:
            continue
        proj_val = proj_info.get("proj_served", proj_info.get("proj"))
        raw_val = proj_info.get("proj_raw", proj_info.get("proj"))
        try:
            proj_val = float(proj_val)
        except (TypeError, ValueError):
            continue
        actual_val = actuals[pid]
        error = actual_val - proj_val
        abs_error = abs(error)
        sq_error = error ** 2

        pos = proj_info.get("pos", "?")
        fdr = proj_info.get("fdr")
        stats = actual_stats.get(pid, {}) or {}

        errors.append({
            "pid": pid,
            "name": proj_info.get("web_name", pid),
            "pos": pos,
            "fdr": fdr,
            "proj": proj_val,
            "proj_raw": raw_val,
            "actual": actual_val,
            "error": error,
            "minutes": stats.get("minutes"),
            "price": proj_info.get("price"),
            "selected_by": proj_info.get("selected_by"),
        })

        by_pos.setdefault(pos, []).append(abs_error)
        if fdr is not None:
            by_fdr.setdefault(str(fdr), []).append(abs_error)

    if not errors:
        return None

    abs_errors = [abs(float(e["error"])) for e in errors]
    sq_errors = [float(e["error"]) ** 2 for e in errors]

    # Top-K: the decision-relevant slice.  MAE over all 500 players hides
    # exactly the bias that hurts captaincy.
    top_k = {}
    ranked = sorted(errors, key=lambda e: -e["proj"])
    for k in (5, 10, 20, 50):
        if len(ranked) < k:
            continue
        rows = ranked[:k]
        top_k[str(k)] = {
            "n": k,
            "mae": round(sum(abs(r["error"]) for r in rows) / k, 3),
            "bias": round(sum(r["error"] for r in rows) / k, 3),
            "mean_proj": round(sum(r["proj"] for r in rows) / k, 3),
            "mean_actual": round(sum(r["actual"] for r in rows) / k, 3),
        }

    # Decile calibration (10 equal-size bins ordered by projection).
    deciles = []
    ordered = sorted(errors, key=lambda e: e["proj"])
    n = len(ordered)
    for i in range(10):
        chunk = ordered[i * n // 10:(i + 1) * n // 10]
        if not chunk:
            continue
        deciles.append({
            "decile": i + 1,
            "n": len(chunk),
            "proj": round(sum(r["proj"] for r in chunk) / len(chunk), 3),
            "actual": round(sum(r["actual"] for r in chunk) / len(chunk), 3),
            "bias": round(sum(r["error"] for r in chunk) / len(chunk), 3),
        })

    # Captain regret proxy: top projected player vs best actual in the pool.
    captain = None
    if ranked:
        top = ranked[0]
        oracle = max(errors, key=lambda e: e["actual"])
        captain = {
            "id": top.get("pid"),
            "name": top.get("name"),
            "proj": top.get("proj"),
            "actual": top.get("actual"),
            "oracle_id": oracle.get("pid"),
            "oracle_name": oracle.get("name"),
            "oracle_actual": oracle.get("actual"),
            "regret": round(float(oracle["actual"]) - float(top["actual"]), 2),
        }

    metrics = {
        "version": 2,
        "n": len(errors),
        "mae": round(sum(abs_errors) / len(abs_errors), 3),
        "rmse": round(math.sqrt(sum(sq_errors) / len(sq_errors)), 3),
        "bias": round(sum(float(e["error"]) for e in errors) / len(errors), 3),
        "by_pos": {pos: round(sum(v) / len(v), 3) for pos, v in by_pos.items()},
        "by_fdr": {fdr: round(sum(v) / len(v), 3) for fdr, v in by_fdr.items()},
        "by_price": _group_errors(errors, lambda e: _price_bucket(e.get("price"))),
        "by_ownership": _group_errors(errors, lambda e: _ownership_bucket(e.get("selected_by"))),
        "top_k": top_k,
        "deciles": deciles,
        "spearman": _spearman([e["proj"] for e in errors], [e["actual"] for e in errors]),
        "captain": captain,
        "top_overestimate": sorted(errors, key=lambda e: e["error"])[:5],
        "top_underestimate": sorted(errors, key=lambda e: e["error"], reverse=True)[:5],
        "has_actual_stats": bool(actual_stats),
    }

    entry["metrics"] = metrics
    entry["computed_at"] = time.time()
    _save(data)
    return metrics


def history():
    """Return all recorded accuracy data."""
    data = _load()
    out = []
    for key in sorted(data.keys()):
        if not key.startswith("gw_"):
            continue
        gw_id = int(key.split("_")[1])
        entry = data[key]
        metrics = entry.get("metrics")
        needs_upgrade = (
            metrics is None
            or int(metrics.get("version", 1)) < 2
        )
        if needs_upgrade and "actuals" in entry:
            # Recompute older metrics to add top-K/bias/calibration fields.
            metrics = compute_accuracy(gw_id)
        try:
            snap_list = snapshots.list_snapshots(gw_id)
        except Exception:
            snap_list = []
        out.append({
            "gw": gw_id,
            "saved_at": entry.get("saved_at"),
            "has_projections": "projections" in entry,
            "has_actuals": "actuals" in entry,
            "metrics": metrics,
            "snapshot_count": len(snap_list),
            "latest_snapshot": snap_list[-1] if snap_list else None,
        })
    return out


def auto_update_history():
    """Automatically fetch actuals and compute accuracy for all past GWs.

    Called on dashboard load to keep accuracy data fresh.
    Processes any GW that has projections saved but no actuals yet.
    Returns: number of GWs newly updated.
    """
    data = _load()
    updated = 0

    for key in sorted(data.keys()):
        if not key.startswith("gw_"):
            continue
        gw_id = int(key.split("_")[1])
        entry = data[key]

        # Skip only if already has actuals and up-to-date metrics.
        if "actuals" in entry and isinstance(entry.get("metrics"), dict) \
                and int(entry["metrics"].get("version", 1)) >= 2:
            continue

        # Skip if no projections saved
        if "projections" not in entry:
            continue

        # Try to fetch actuals for this GW
        if "actuals" not in entry:
            actuals = fetch_actuals(gw_id)
            if actuals is None:
                continue  # GW not finished yet
            data[key]["actuals"] = actuals
            _save(data)

        # Compute/upgrade metrics if we have actuals.
        current_metrics = entry.get("metrics")
        if not isinstance(current_metrics, dict) or int(current_metrics.get("version", 1)) < 2:
            metrics = compute_accuracy(gw_id)
            if metrics:
                updated += 1

    return updated


def suggested_weights():
    """Based on historical accuracy, suggest weight adjustments.

    Returns dict with suggested weights and reasoning.
    """
    hist = history()
    completed = [h for h in hist if h["metrics"] is not None]
    if len(completed) < 3:
        return {
            "status": "insufficient_data",
            "message": f"Perlu minimal 3 GW dengan data aktual untuk analisis. Saat ini: {len(completed)} GW.",
            "weights": None,
        }

    # Aggregate MAE by position across all GWs
    pos_maes = {}
    fdr_maes = {}
    overall_maes = []
    for h in completed:
        m = h.get("metrics")
        if not isinstance(m, dict):
            continue
        overall_maes.append(float(m.get("mae", 0)))
        for pos, mae in m.get("by_pos", {}).items():
            pos_maes.setdefault(pos, []).append(float(mae))
        for fdr, mae in m.get("by_fdr", {}).items():
            fdr_maes.setdefault(str(fdr), []).append(float(mae))

    avg_mae = round(sum(overall_maes) / len(overall_maes), 3)
    pos_avg = {pos: round(sum(v) / len(v), 3) for pos, v in pos_maes.items()}
    fdr_avg = {fdr: round(sum(v) / len(v), 3) for fdr, v in fdr_maes.items()}

    suggestions = []
    # If FDR extreme values (1, 5) have higher MAE than middle (3), FDR multipliers are too aggressive
    fdr_mid = fdr_avg.get("3", avg_mae)
    fdr_easy = fdr_avg.get("1", fdr_avg.get("2", fdr_mid))
    fdr_hard = fdr_avg.get("5", fdr_avg.get("4", fdr_mid))
    if fdr_easy > fdr_mid * 1.2 or fdr_hard > fdr_mid * 1.2:
        suggestions.append("FDR multiplier terlalu agresif — pertimbangkan 1.08/0.90 (dari 1.12/0.85)")

    # If GK/DEF MAE is much higher than MID/FWD, CS model needs tuning
    def_mae = pos_avg.get("DEF", avg_mae)
    mid_mae = pos_avg.get("MID", avg_mae)
    if def_mae > mid_mae * 1.3:
        suggestions.append("CS probability terlalu optimis untuk DEF — kurangi CS weight")

    # Trend analysis
    recent = overall_maes[-3:]
    early = overall_maes[:3] if len(overall_maes) >= 6 else overall_maes[:len(overall_maes)//2+1]
    if sum(recent) / len(recent) < sum(early) / len(early) * 0.9:
        suggestions.append("Model semakin akurat seiring musim — form data makin reliable")

    return {
        "status": "ok",
        "n_gws": len(completed),
        "avg_mae": avg_mae,
        "by_pos": pos_avg,
        "by_fdr": fdr_avg,
        "suggestions": suggestions,
        "weights": None,  # Could return actual adjusted weights in future
    }
