"""Historical accuracy tracking for FPL projections.

Saves projections before each GW, fetches actuals after GW finishes,
computes accuracy metrics, and suggests weight adjustments.
"""

import json
import math
import time
from pathlib import Path

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


def save_projections(gw_id, df):
    """Save projections for a GW before it starts.

    Call this when loading data on Beranda (before deadline).
    Only saves once per GW to avoid overwriting with stale post-deadline data.
    """
    data = _load()
    key = f"gw_{gw_id}"
    if key in data and "projections" in data[key]:
        # Already saved for this GW — don't overwrite
        return False
    projections = {}
    for _, row in df.iterrows():
        if row["proj"] is not None and not (isinstance(row["proj"], float) and math.isnan(row["proj"])):
            projections[str(int(row["id"]))] = {
                "proj": round(float(row["proj"]), 2),
                "pos": row["pos"],
                "fdr": int(row["fdr"]) if row.get("fdr") is not None else None,
                "web_name": row["web_name"],
                "team_short": row["team_short"],
            }
    data[key] = {
        "saved_at": time.time(),
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


def compute_accuracy(gw_id):
    """Compute accuracy metrics for a completed GW.

    Returns dict with MAE, RMSE, and breakdowns by position and FDR.
    """
    data = _load()
    key = f"gw_{gw_id}"
    if key not in data or "projections" not in data[key]:
        return None

    # Fetch actuals if not already stored
    if "actuals" not in data[key]:
        actuals = fetch_actuals(gw_id)
        if actuals is None:
            return None
        data[key]["actuals"] = actuals
        _save(data)
    else:
        actuals = data[key]["actuals"]

    projections = data[key]["projections"]

    errors = []
    by_pos = {}
    by_fdr = {}

    for pid, proj_info in projections.items():
        if pid not in actuals:
            continue
        proj_val = proj_info["proj"]
        actual_val = actuals[pid]
        error = actual_val - proj_val
        abs_error = abs(error)
        sq_error = error ** 2

        pos = proj_info.get("pos", "?")
        fdr = proj_info.get("fdr")

        errors.append({"pid": pid, "name": proj_info.get("web_name", pid),
                        "pos": pos, "fdr": fdr, "proj": proj_val,
                        "actual": actual_val, "error": error})

        by_pos.setdefault(pos, []).append(abs_error)
        if fdr is not None:
            by_fdr.setdefault(str(fdr), []).append(abs_error)

    if not errors:
        return None

    abs_errors = [abs(float(e["error"])) for e in errors]
    sq_errors = [float(e["error"]) ** 2 for e in errors]

    metrics = {
        "n": len(errors),
        "mae": round(sum(abs_errors) / len(abs_errors), 3),
        "rmse": round(math.sqrt(sum(sq_errors) / len(sq_errors)), 3),
        "by_pos": {pos: round(sum(v) / len(v), 3) for pos, v in by_pos.items()},
        "by_fdr": {fdr: round(sum(v) / len(v), 3) for fdr, v in by_fdr.items()},
        "top_overestimate": sorted(errors, key=lambda e: e["error"])[:5],
        "top_underestimate": sorted(errors, key=lambda e: e["error"], reverse=True)[:5],
    }

    data[key]["metrics"] = metrics
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
        if metrics is None and "actuals" in entry:
            # Try to compute
            metrics = compute_accuracy(gw_id)
        out.append({
            "gw": gw_id,
            "saved_at": entry.get("saved_at"),
            "has_projections": "projections" in entry,
            "has_actuals": "actuals" in entry,
            "metrics": metrics,
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

        # Skip if already has actuals and metrics
        if "actuals" in entry and "metrics" in entry:
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

        # Compute metrics if we have actuals but no metrics
        if "metrics" not in entry or entry.get("metrics") is None:
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
