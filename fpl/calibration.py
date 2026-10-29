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


# ---------------------------------------------------------------------------
# Alternative calibrators
# ---------------------------------------------------------------------------
# A global linear map failed out-of-sample (the relationship is non-linear:
# mid-range projections were under-predicted, the top decile over-predicted).
# A piecewise "top-end shrink" often helps: values above T are compressed
# toward T by a factor F.  It is still a simple, monotone map and can be
# validated leave-one-GW-out.


def _apply_shrink_value(proj, t, f):
    proj = max(0.0, float(proj))
    if proj <= t:
        return proj
    return t + float(f) * (proj - t)


def _mae_shrink(pairs, t, f):
    if not pairs:
        return None
    errs = [abs(p["actual"] - _apply_shrink_value(p["proj"], t, f)) for p in pairs]
    return sum(errs) / len(errs)


def _fit_shrink(pairs):
    """Choose (threshold, factor) on the supplied rows."""
    if len(pairs) < 20:
        return None
    best = None
    # Keep the shrink moderate.  An unconstrained grid chooses ~0.45x above
    # 3.0, which minimises MAE (median-like) but destroys captain upside.
    for t in (4.0, 4.5, 5.0, 5.5, 6.0, 7.0):
        for f in (0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95):
            mae = _mae_shrink(pairs, t, f)
            if mae is not None and (best is None or mae < best[0]):
                best = (mae, t, f)
    return (best[1], best[2]) if best else None


def _fit_candidate(pairs, method):
    if method == "linear":
        return _fit_linear(pairs)
    if method == "shrink":
        return _fit_shrink(pairs)
    return None


def _predict(pair, method, params):
    if params is None:
        return pair["proj"]
    if method == "linear":
        a, b = params
        return max(0.0, a + b * pair["proj"])
    if method == "shrink":
        t, f = params
        return _apply_shrink_value(pair["proj"], t, f)
    return pair["proj"]


def _cv_mae(samples, gws, method):
    """Leave-one-GW-out MAE for a candidate calibrator."""
    errs = []
    for gw in gws:
        train = [s for s in samples if s["gw"] != gw]
        test = [s for s in samples if s["gw"] == gw]
        if len(train) < 30 or not test:
            continue
        params = _fit_candidate(train, method)
        if params is None:
            continue
        errs.extend(abs(s["actual"] - _predict(s, method, params)) for s in test)
    if not errs:
        return None
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

    # Leave-one-GW-out: fit every candidate on the rest, evaluate on the
    # held-out GW.  Raw errors are collected on exactly the same rows.
    raw_errs = []
    for gw in gws:
        test = [s for s in samples if s["gw"] == gw]
        raw_errs.extend(abs(s["actual"] - s["proj"]) for s in test)
    raw_mae_cv = sum(raw_errs) / len(raw_errs) if raw_errs else None

    candidate_maes = {}
    for method in ("linear", "shrink"):
        mae = _cv_mae(samples, gws, method)
        if mae is not None:
            candidate_maes[method] = mae

    if not candidate_maes:
        result = {"enabled": False, "status": "fit_failed", "n": n, "gws": gws}
        if save:
            _save(result)
        return result

    best_method = min(candidate_maes, key=candidate_maes.get)
    cal_mae_cv = candidate_maes[best_method]
    improvement = None
    if raw_mae_cv and cal_mae_cv is not None:
        improvement = round((raw_mae_cv - cal_mae_cv) / raw_mae_cv * 100, 2)

    enabled = bool(improvement is not None and improvement >= MIN_IMPROVEMENT_PCT)

    # Fit the chosen method on the full history for serving.
    final_params = _fit_candidate(samples, best_method)
    if final_params is None:
        result = {"enabled": False, "status": "fit_failed", "n": n, "gws": gws}
        if save:
            _save(result)
        return result

    if best_method == "linear":
        glob = {"a": round(final_params[0], 4), "b": round(final_params[1], 4), "n": n}
    elif best_method == "shrink":
        glob = {"t": round(final_params[0], 3), "f": round(final_params[1], 3), "n": n}
    else:
        glob = {"n": n}

    # Per-position coefficients are kept for diagnostics and older code paths.
    by_pos = {}
    for pos in ("GK", "DEF", "MID", "FWD"):
        pairs = [s for s in samples if s["pos"] == pos]
        if len(pairs) < MIN_SAMPLES_POS:
            continue
        fitted = _fit_candidate(pairs, best_method)
        if not fitted:
            continue
        if best_method == "linear":
            by_pos[pos] = {"a": round(fitted[0], 4), "b": round(fitted[1], 4), "n": len(pairs)}
        elif best_method == "shrink":
            by_pos[pos] = {"t": round(fitted[0], 3), "f": round(fitted[1], 3), "n": len(pairs)}

    result = {
        "enabled": enabled,
        "status": "ok",
        "method": best_method,
        "apply_by_pos": False,
        "global": glob,
        "by_pos": by_pos,
        "metrics": {
            "n": n,
            "gws": gws,
            "raw_mae_cv": round(raw_mae_cv, 3) if raw_mae_cv else None,
            "calibrated_mae_cv": round(cal_mae_cv, 3) if cal_mae_cv else None,
            "improvement_pct": improvement,
            "min_improvement_pct": MIN_IMPROVEMENT_PCT,
            "by_method": {k: round(v, 3) for k, v in candidate_maes.items()},
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
        "method": params.get("method", "linear"),
        "by_method": m.get("by_method"),
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
    method = params.get("method", "linear")
    apply_by_pos = bool(params.get("apply_by_pos", True))

    out = df.copy()
    raw = out["proj"]
    import pandas as pd

    proj = pd.to_numeric(raw, errors="coerce")

    def _calibrate(series, prm):
        if method == "shrink" and "t" in prm and "f" in prm:
            t, f = float(prm["t"]), float(prm["f"])
            return series.where(series <= t, t + f * (series - t))
        if "a" in prm and "b" in prm:
            return float(prm["a"]) + float(prm["b"]) * series
        return series

    cal = pd.Series(index=out.index, dtype="float64")
    if apply_by_pos and by_pos:
        for pos, idx in out.groupby("pos").groups.items():
            prm = by_pos.get(pos, g)
            cal.loc[idx] = _calibrate(proj.loc[idx], prm)
    else:
        cal = _calibrate(proj, g)

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
