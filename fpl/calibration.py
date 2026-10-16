"""Point-projection calibration against realised scores.

The projection model can be systematically over- or under-confident in
aggregate (e.g. early-season form inflated, DefCon under-priced). This module
fits a simple per-position linear map ``actual ~ a + b * proj`` on all
completed Gameweeks recorded in `accuracy.json`, shrunk toward the identity so
that small samples cannot distort projections, and validated with a
leave-one-Gameweek-out check. Calibration is only applied when it actually
improved out-of-sample MAE.
"""

import json
import math
import time

from .api import DATA_DIR

FILE = DATA_DIR / "calibration.json"

# Shrinkage strength in pseudo-observations toward identity (y = x).
SHRINK_K = 60.0
MIN_SAMPLES = 120
MIN_SAMPLES_POS = 60
MIN_GWS = 4
MIN_IMPROVEMENT_PCT = 0.5

SLOPE_BOUNDS = (0.45, 1.35)
INTERCEPT_BOUNDS = (-3.0, 3.0)


def _samples():
    """Raw projection -> actual pairs from the recorded accuracy history."""
    from .accuracy import _load as load_accuracy

    data = load_accuracy()
    out = []
    for key in sorted(data.keys()):
        if not key.startswith("gw_"):
            continue
        entry = data[key]
        projections = entry.get("projections", {})
        actuals = entry.get("actuals", {})
        if not projections or not actuals:
            continue
        gw = int(key.split("_")[1])
        for pid, info in projections.items():
            if pid not in actuals:
                continue
            proj = info.get("proj")
            if proj is None or proj <= 0:
                continue
            out.append({
                "gw": gw,
                "pid": pid,
                "pos": info.get("pos", "MID"),
                "proj": float(proj),
                "actual": float(actuals[pid]),
            })
    return out


def _fit_linear(pairs, k=SHRINK_K):
    """Least-squares a + b*x with pseudo-points pulling toward identity."""
    n = len(pairs)
    if n < 20:
        return None
    mx = sum(p["proj"] for p in pairs) / n
    xs = [p["proj"] for p in pairs]
    ys = [p["actual"] for p in pairs]
    # Pseudo observations at (mean, mean) keep small samples near identity.
    for _ in range(int(min(k, n))):
        xs.append(mx)
        ys.append(mx)
    m = len(xs)
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = m * sxx - sx * sx
    if abs(denom) < 1e-9:
        return None
    b = (m * sxy - sx * sy) / denom
    a = (sy - b * sx) / m
    b = max(SLOPE_BOUNDS[0], min(SLOPE_BOUNDS[1], b))
    a = max(INTERCEPT_BOUNDS[0], min(INTERCEPT_BOUNDS[1], a))
    return a, b


def _mae(pairs, a, b):
    if not pairs:
        return None
    errs = [abs(p["actual"] - max(0.0, a + b * p["proj"])) for p in pairs]
    return sum(errs) / len(errs)


def fit(save=True):
    """Fit calibration on the full history with leave-one-GW-out validation.

    Returns a result dict (also saved unless save=False).
    """
    samples = _samples()
    gws = sorted({s["gw"] for s in samples})
    n = len(samples)
    if n < MIN_SAMPLES or len(gws) < MIN_GWS:
        result = {
            "enabled": False,
            "status": "insufficient_data",
            "message": f"Perlu ≥{MIN_SAMPLES} sampel di ≥{MIN_GWS} GW (saat ini {n} sampel, {len(gws)} GW).",
            "n": n,
            "gws": gws,
        }
        if save:
            _save(result)
        return result

    glob = _fit_linear(samples)
    if glob is None:
        result = {"enabled": False, "status": "fit_failed", "n": n, "gws": gws}
        if save:
            _save(result)
        return result

    # Leave-one-GW-out: fit on the rest, evaluate on the held-out GW.
    raw_errs, cal_errs = [], []
    for gw in gws:
        train = [s for s in samples if s["gw"] != gw]
        test = [s for s in samples if s["gw"] == gw]
        if len(train) < 30 or not test:
            continue
        fit_g = _fit_linear(train)
        if fit_g is None:
            continue
        a, b = fit_g
        raw_errs.extend(abs(t["actual"] - t["proj"]) for t in test)
        cal_errs.extend(abs(t["actual"] - max(0.0, a + b * t["proj"])) for t in test)

    raw_mae_cv = sum(raw_errs) / len(raw_errs) if raw_errs else None
    cal_mae_cv = sum(cal_errs) / len(cal_errs) if cal_errs else None
    improvement = None
    if raw_mae_cv and cal_mae_cv is not None:
        improvement = round((raw_mae_cv - cal_mae_cv) / raw_mae_cv * 100, 2)

    enabled = bool(improvement is not None and improvement >= MIN_IMPROVEMENT_PCT)

    by_pos = {}
    for pos in ("GK", "DEF", "MID", "FWD"):
        pairs = [s for s in samples if s["pos"] == pos]
        if len(pairs) >= MIN_SAMPLES_POS:
            f = _fit_linear(pairs)
            if f:
                by_pos[pos] = {"a": round(f[0], 4), "b": round(f[1], 4), "n": len(pairs)}

    result = {
        "enabled": enabled,
        "status": "ok",
        "global": {"a": round(glob[0], 4), "b": round(glob[1], 4), "n": n},
        "by_pos": by_pos,
        "metrics": {
            "n": n,
            "gws": gws,
            "raw_mae_cv": round(raw_mae_cv, 3) if raw_mae_cv else None,
            "calibrated_mae_cv": round(cal_mae_cv, 3) if cal_mae_cv else None,
            "improvement_pct": improvement,
            "min_improvement_pct": MIN_IMPROVEMENT_PCT,
        },
        "fitted_at": time.time(),
    }
    if save:
        _save(result)
    return result


def _save(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data, indent=2))


def load():
    if FILE.exists():
        try:
            return json.loads(FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def status():
    params = load()
    if not params:
        return {"available": False, "message": "Kalibrasi belum di-fit."}
    m = params.get("metrics", {})
    return {
        "available": True,
        "enabled": bool(params.get("enabled")),
        "n": m.get("n"),
        "gws": m.get("gws"),
        "raw_mae_cv": m.get("raw_mae_cv"),
        "calibrated_mae_cv": m.get("calibrated_mae_cv"),
        "improvement_pct": m.get("improvement_pct"),
        "fitted_at": params.get("fitted_at"),
        "global": params.get("global"),
        "by_pos": params.get("by_pos", {}),
    }


def apply(df, params=None):
    """Apply calibration to a projection table.

    When calibration is enabled, adds `proj_pre_cal` (raw) and `proj_cal`
    columns and replaces `proj` (the served value) with the calibrated one.
    When disabled/absent the DataFrame is returned unchanged.
    """
    if params is None:
        params = load()
    if not params or not params.get("enabled"):
        return df

    g = params.get("global")
    if not g:
        return df
    by_pos = params.get("by_pos", {})

    out = df.copy()
    raw = out["proj"]
    import pandas as pd

    proj = pd.to_numeric(raw, errors="coerce")
    cal = pd.Series(index=out.index, dtype="float64")
    for pos, idx in out.groupby("pos").groups.items():
        prm = by_pos.get(pos, g)
        a, b = float(prm["a"]), float(prm["b"])
        cal.loc[idx] = a + b * proj.loc[idx]

    # Never below zero; respect the position ceiling when available.
    try:
        from .model import POS_CEILING

        ceil = out.apply(
            lambda r: POS_CEILING.get(r["pos"], 14) * int(r.get("n_fixtures") or 1),
            axis=1,
        )
        cal = cal.clip(lower=0.0)
        cal = pd.concat([cal, ceil], axis=1).min(axis=1)
    except Exception:
        cal = cal.clip(lower=0.0)

    out["proj_pre_cal"] = proj
    out["proj_cal"] = cal.round(2)
    out["proj"] = out["proj_cal"].where(proj.notna(), other=proj)
    out["proj"] = pd.to_numeric(out["proj"], errors="coerce")
    return out
