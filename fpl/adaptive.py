"""Adaptive weight optimization for the FPL projection model.

Uses historical projection vs actual data to find optimal model weights
that minimize prediction error (MAE).
"""

import json
import math
from itertools import product
from pathlib import Path

from .api import DATA_DIR

WEIGHTS_FILE = DATA_DIR / "tuned_weights.json"

# Default weights (from model.py)
DEFAULT_WEIGHTS = {
    "form_w": 0.40,
    "ppg_w": 0.20,
    "xgi_w": 0.25,
    "ict_w": 0.15,
    "own_w": 0.65,
    "ep_w": 0.25,
    "safety_w": 0.10,
    "fdr_mult": {1: 1.12, 2: 1.06, 3: 1.0, 4: 0.92, 5: 0.85},
    "cs_weight": 0.15,
    "threat_weight": 0.08,
    "bonus_weight": 0.08,
    "creativity_weight": 0.06,
}


def load_tuned_weights():
    """Load tuned weights from file, return None if not available."""
    if WEIGHTS_FILE.exists():
        try:
            data = json.loads(WEIGHTS_FILE.read_text())
            if data.get("weights"):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return None


def save_tuned_weights(weights, metrics):
    """Save tuned weights to data/tuned_weights.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    import time
    data = {
        "weights": weights,
        "metrics": metrics,
        "saved_at": time.time(),
    }
    WEIGHTS_FILE.write_text(json.dumps(data, indent=2))
    return data


def get_active_weights():
    """Get the currently active weights (tuned if available and enabled, else default)."""
    tuned = load_tuned_weights()
    if tuned and tuned.get("weights") and tuned.get("metrics", {}).get("enabled"):
        return tuned["weights"]
    return DEFAULT_WEIGHTS.copy()


def _build_training_data():
    """Extract training data from accuracy.json.

    Returns list of dicts with features and actual points for each player-GW pair.
    """
    from .accuracy import _load as load_accuracy

    data = load_accuracy()
    samples = []

    for key in sorted(data.keys()):
        if not key.startswith("gw_"):
            continue
        entry = data[key]
        projections = entry.get("projections", {})
        actuals = entry.get("actuals", {})

        if not projections or not actuals:
            continue

        for pid, proj_info in projections.items():
            if pid not in actuals:
                continue
            actual = actuals[pid]
            samples.append({
                "pid": pid,
                "gw": key,
                "proj": proj_info["proj"],
                "pos": proj_info.get("pos", "MID"),
                "fdr": proj_info.get("fdr"),
                "actual": actual,
            })

    return samples


def _simulate_projection(features, weights):
    """Simulate a projection using given weights.

    This is a simplified simulation — we can't fully reconstruct the projection
    pipeline without raw player data, but we can estimate the relative impact
    of weight changes on the final projection.

    For adaptive tuning, we scale the existing projection by how much the
    weights deviate from default.
    """
    orig_proj = features["proj"]
    if orig_proj <= 0:
        return 0.0

    # Compute FDR adjustment factor
    fdr = features.get("fdr")
    if fdr is not None:
        default_fdr_mult = DEFAULT_WEIGHTS["fdr_mult"].get(fdr, 1.0)
        new_fdr_mult = weights.get("fdr_mult", DEFAULT_WEIGHTS["fdr_mult"]).get(str(fdr), default_fdr_mult)
        if isinstance(weights.get("fdr_mult"), dict):
            new_fdr_mult = weights["fdr_mult"].get(str(fdr), weights["fdr_mult"].get(fdr, default_fdr_mult))
        fdr_ratio = new_fdr_mult / default_fdr_mult if default_fdr_mult != 0 else 1.0
    else:
        fdr_ratio = 1.0

    # Scale blend weights
    default_own = DEFAULT_WEIGHTS["own_w"]
    default_ep = DEFAULT_WEIGHTS["ep_w"]
    new_own = weights.get("own_w", default_own)
    new_ep = weights.get("ep_w", default_ep)

    # Approximate: original projection was made with default blend
    # Reblend using new weights (simplified)
    blend_ratio = (new_own + new_ep) / (default_own + default_ep) if (default_own + default_ep) > 0 else 1.0

    adjusted = orig_proj * fdr_ratio * blend_ratio
    return round(adjusted, 2)


def optimize_weights(progress_callback=None):
    """Find optimal weights by grid search over key parameters.

    Grid searches over:
    - FDR multiplier extremes (how aggressive FDR impact is)
    - Blend weights (own model vs FPL ep_next)

    Returns: dict with optimal weights and comparison metrics.
    """
    samples = _build_training_data()
    if len(samples) < 20:
        return {
            "status": "insufficient_data",
            "message": f"Perlu minimal 20 data poin (saat ini {len(samples)}). Tunggu lebih banyak GW selesai.",
            "n_samples": len(samples),
        }

    # Grid search parameters
    fdr_easy_range = [1.08, 1.10, 1.12, 1.14, 1.16]
    fdr_hard_range = [0.80, 0.83, 0.85, 0.88, 0.90]
    own_w_range = [0.55, 0.60, 0.65, 0.70, 0.75]
    ep_w_range = [0.15, 0.20, 0.25, 0.30]

    # Compute default MAE first
    default_errors = [abs(s["actual"] - s["proj"]) for s in samples]
    default_mae = sum(default_errors) / len(default_errors)
    default_rmse = math.sqrt(sum(e ** 2 for e in default_errors) / len(default_errors))

    best_mae = default_mae
    best_weights = DEFAULT_WEIGHTS.copy()
    total_combos = len(fdr_easy_range) * len(fdr_hard_range) * len(own_w_range) * len(ep_w_range)
    tested = 0

    for fdr_easy, fdr_hard, own_w, ep_w in product(
        fdr_easy_range, fdr_hard_range, own_w_range, ep_w_range
    ):
        safety_w = max(1.0 - own_w - ep_w, 0.0)
        if safety_w < 0:
            continue

        test_weights = DEFAULT_WEIGHTS.copy()
        test_weights["fdr_mult"] = {
            1: round(fdr_easy, 2),
            2: round(1.0 + (fdr_easy - 1.0) * 0.5, 2),
            3: 1.0,
            4: round(1.0 - (1.0 - fdr_hard) * 0.5, 2),
            5: round(fdr_hard, 2),
        }
        test_weights["own_w"] = own_w
        test_weights["ep_w"] = ep_w
        test_weights["safety_w"] = round(safety_w, 2)

        # Evaluate
        errors = []
        for s in samples:
            simulated = _simulate_projection(s, test_weights)
            errors.append(abs(s["actual"] - simulated))

        mae = sum(errors) / len(errors)

        if mae < best_mae:
            best_mae = mae
            best_weights = test_weights.copy()

        tested += 1
        if progress_callback and tested % 100 == 0:
            progress_callback(tested / total_combos)

    if progress_callback:
        progress_callback(1.0)

    # Compute tuned RMSE
    tuned_errors = []
    for s in samples:
        simulated = _simulate_projection(s, best_weights)
        tuned_errors.append(abs(s["actual"] - simulated))
    tuned_mae = sum(tuned_errors) / len(tuned_errors)
    tuned_rmse = math.sqrt(sum(e ** 2 for e in tuned_errors) / len(tuned_errors))

    improvement = round((default_mae - tuned_mae) / default_mae * 100, 1)

    result = {
        "status": "ok",
        "n_samples": len(samples),
        "n_combos_tested": tested,
        "default_mae": round(default_mae, 3),
        "default_rmse": round(default_rmse, 3),
        "tuned_mae": round(tuned_mae, 3),
        "tuned_rmse": round(tuned_rmse, 3),
        "improvement_pct": improvement,
        "weights": best_weights,
    }

    return result


def compare_weights(default_weights, tuned_weights):
    """Compare two sets of weights and return a diff table.

    Returns list of {param, default, tuned, change}.
    """
    params = [
        ("form_w", "Bobot Form"),
        ("ppg_w", "Bobot PPG"),
        ("xgi_w", "Bobot xGI"),
        ("ict_w", "Bobot ICT"),
        ("own_w", "Blend: Model Sendiri"),
        ("ep_w", "Blend: ep_next FPL"),
        ("safety_w", "Blend: Safety"),
        ("cs_weight", "CS Bonus Weight"),
        ("threat_weight", "Threat Weight"),
        ("bonus_weight", "Bonus Weight"),
        ("creativity_weight", "Creativity Weight"),
    ]

    rows = []
    for key, label in params:
        d = default_weights.get(key, 0)
        t = tuned_weights.get(key, d)
        change = round(t - d, 3)
        rows.append({
            "param": label,
            "key": key,
            "default": d,
            "tuned": t,
            "change": change,
            "change_pct": round(change / d * 100, 1) if d != 0 else 0,
        })

    # FDR mult comparison
    default_fdr = default_weights.get("fdr_mult", {})
    tuned_fdr = tuned_weights.get("fdr_mult", {})
    for fdr_val in [1, 2, 3, 4, 5]:
        d = default_fdr.get(fdr_val, default_fdr.get(str(fdr_val), 1.0))
        t = tuned_fdr.get(fdr_val, tuned_fdr.get(str(fdr_val), d))
        change = round(t - d, 3)
        rows.append({
            "param": f"FDR {fdr_val} Multiplier",
            "key": f"fdr_{fdr_val}",
            "default": d,
            "tuned": t,
            "change": change,
            "change_pct": round(change / d * 100, 1) if d != 0 else 0,
        })

    return rows
