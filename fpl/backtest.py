"""Small walk-forward / baseline evaluation helpers.

The dashboard previously reported only MAE/RMSE.  This module adds a
decision-oriented comparison table: current projection vs simple baselines,
top-K bias, rank correlation and a moderate top-end shrink.

It is intentionally read-only and uses whatever fields exist in
``accuracy.json`` so older files keep working.
"""

from __future__ import annotations

import math

from .accuracy import _load, _spearman


def load_pairs(served=True):
    """Flatten accuracy history into one row per player-GW."""
    data = _load()
    rows = []
    for key in sorted(data.keys()):
        if not key.startswith("gw_"):
            continue
        gw = int(key.split("_")[1])
        entry = data[key]
        projections = entry.get("projections", {})
        actuals = entry.get("actuals", {})
        if not projections or not actuals:
            continue
        for pid, info in projections.items():
            if pid not in actuals:
                continue
            proj = info.get("proj_served", info.get("proj")) if served else info.get("proj")
            try:
                proj = float(proj)
            except (TypeError, ValueError):
                continue
            raw = info.get("proj")
            try:
                raw = float(raw)
            except (TypeError, ValueError):
                raw = proj
            rows.append({
                "gw": gw,
                "pid": pid,
                "pos": info.get("pos", "MID"),
                "fdr": info.get("fdr"),
                "proj": proj,
                "raw_proj": raw,
                "actual": float(actuals[pid]),
                "ep_next": info.get("ep_next"),
                "form": info.get("form"),
                "ppg": info.get("ppg"),
                "selected_by": info.get("selected_by"),
            })
    return rows


def _topk(rows, k=10):
    """Top-K within each Gameweek (not top-K across the whole history)."""
    by_gw = {}
    for r in rows:
        by_gw.setdefault(r["gw"], []).append(r)
    picked = []
    for gw_rows in by_gw.values():
        picked.extend(sorted(gw_rows, key=lambda r: -r["pred"])[:k])
    if not picked:
        return None
    return {
        "n": len(picked),
        "mae": round(sum(abs(r["actual"] - r["pred"]) for r in picked) / len(picked), 3),
        "bias": round(sum(r["actual"] - r["pred"] for r in picked) / len(picked), 3),
    }


def metrics(rows, pred_key="pred"):
    rows = [r for r in rows if r.get(pred_key) is not None]
    if not rows:
        return None
    errs = [r["actual"] - r[pred_key] for r in rows]
    abs_errs = [abs(e) for e in errs]
    return {
        "n": len(rows),
        "mae": round(sum(abs_errs) / len(abs_errs), 3),
        "rmse": round(math.sqrt(sum(e * e for e in errs) / len(errs)), 3),
        "bias": round(sum(errs) / len(errs), 3),
        "spearman": _spearman([r[pred_key] for r in rows], [r["actual"] for r in rows]),
        "top10": _topk(rows, 10),
    }


def compare_baselines():
    """Compare served/raw projections and simple alternatives.

    Only sources with enough coverage are returned.
    """
    rows = load_pairs(served=True)
    if not rows:
        return []

    out = []
    candidates = [
        ("Model (served)", lambda r: r["proj"]),
        ("Model (raw)", lambda r: r.get("raw_proj", r["proj"])),
        ("Top-end shrink (t=4, f=0.65)",
         lambda r: r["proj"] if r["proj"] <= 4 else 4 + 0.65 * (r["proj"] - 4)),
        ("Form (FPL)", lambda r: _float(r.get("form"))),
        ("PPG (season)", lambda r: _float(r.get("ppg"))),
        ("ep_next (FPL)", lambda r: _float(r.get("ep_next"))),
    ]
    for name, fn in candidates:
        work = []
        for r in rows:
            try:
                pred = fn(r)
            except Exception:
                pred = None
            if pred is None:
                continue
            work.append({**r, "pred": pred})
        # Require at least 60% coverage, otherwise the comparison is noise.
        if len(work) < max(50, 0.6 * len(rows)):
            continue
        m = metrics(work)
        if m:
            out.append({"model": name, **m})
    return out


def _float(value):
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value):
            return None
        return value
    except (TypeError, ValueError):
        return None
