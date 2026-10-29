"""Machine Learning model for FPL Expected Points (xP) prediction.

Uses Ridge Regression and Gradient Boosting to predict player points
based on historical features, trained from accuracy tracking data.
"""

import json
import math
import pickle
import time
from pathlib import Path

import numpy as np

from .api import DATA_DIR

MODEL_FILE = DATA_DIR / "ml_model.pkl"
MODEL_META_FILE = DATA_DIR / "ml_model_meta.json"

# Feature columns used for training (must match what's available in accuracy.json projections)
# We'll reconstruct features from player data at prediction time
FEATURE_NAMES = [
    "form", "ppg", "xGI_per90", "ict_per_game", "bonus_per_game",
    "creativity_per_game", "threat_norm", "cs_prob", "minutes_factor",
    "selected_by", "price_norm", "fdr", "is_home", "ep_next",
]


# Snapshot columns that may be available.  Older accuracy files only contain
# proj/pos/fdr; the builder keeps only columns with enough coverage so those
# files still produce a valid (small) feature set.
_EXTRA_FEATURES = (
    "own", "ep_next", "form", "ppg", "xgi90", "xg90", "xa90",
    "threat", "xgi_sig", "ict_sig", "bonus", "creativity",
    "cs_prob", "dc_prob", "dc_bonus", "minutes_factor",
    "selected_by", "price", "is_home", "n_fixtures",
)


def _feature_dict(proj_info, proj, pos, fdr):
    features = {
        "proj": float(proj),
        "proj_squared": float(proj) ** 2,
        "proj_log": math.log(max(float(proj), 0.1)),
        "fdr": float(fdr) if fdr is not None else 3.0,
        "fdr_easy": 1.0 if fdr and fdr <= 2 else 0.0,
        "fdr_hard": 1.0 if fdr and fdr >= 4 else 0.0,
        "pos_gk": 1.0 if pos == "GK" else 0.0,
        "pos_def": 1.0 if pos == "DEF" else 0.0,
        "pos_mid": 1.0 if pos == "MID" else 0.0,
        "pos_fwd": 1.0 if pos == "FWD" else 0.0,
    }
    for key in _EXTRA_FEATURES:
        value = proj_info.get(key)
        if value is None:
            continue
        try:
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            features[key] = float(value)
        except (TypeError, ValueError):
            continue
    return features


def _build_training_data():
    """Build training dataset from accuracy history + full feature snapshots.

    Returns: (X, y, feature_names, groups) where groups is the GW id per row.
    """
    from .accuracy import _load as load_accuracy

    data = load_accuracy()
    rows = []
    y_rows = []
    groups = []

    for key in sorted(data.keys()):
        if not key.startswith("gw_"):
            continue
        gw = int(key.split("_")[1])
        entry = data[key]
        projections = entry.get("projections", {})
        actuals = entry.get("actuals", {})

        if not projections or not actuals:
            continue

        for pid, proj_info in projections.items():
            if pid not in actuals:
                continue
            actual = actuals[pid]
            proj = proj_info.get("proj", 0)
            pos = proj_info.get("pos", "MID")
            fdr = proj_info.get("fdr")
            if proj is None or proj <= 0:
                continue
            rows.append(_feature_dict(proj_info, proj, pos, fdr))
            y_rows.append(actual)
            groups.append(gw)

    if not rows:
        return None, None, [], []

    # Keep a feature only when it is present for at least half the samples.
    # This prevents a column that exists in one GW from becoming a constant
    # zero for all other GWs.
    keys = set()
    for row in rows:
        keys.update(row.keys())
    n = len(rows)
    feature_names = []
    for key in sorted(keys):
        coverage = sum(1 for row in rows if key in row)
        if coverage >= max(10, int(0.5 * n)):
            feature_names.append(key)

    X_rows = [[row.get(key, 0.0) for key in feature_names] for row in rows]
    return (
        np.array(X_rows, dtype=np.float64),
        np.array(y_rows, dtype=np.float64),
        feature_names,
        np.array(groups, dtype=np.int64),
    )


def _build_prediction_features(player_data, feature_names):
    """Build a feature vector matching the trained model's columns."""
    proj = float(player_data.get("proj") or 0)
    if proj <= 0:
        return None
    features = _feature_dict(
        player_data,
        proj,
        player_data.get("pos", "MID"),
        player_data.get("fdr"),
    )
    return np.array([[features.get(key, 0.0) for key in feature_names]], dtype=np.float64)


def train_model():
    """Train ML models with Gameweek-grouped cross-validation.

    The old version used random KFold, which leaks information across rows
    from the same Gameweek, and compared GBR CV error against the formula's
    *training* error.  Both are fixed here.  A model is only marked enabled
    when it beats the formula out-of-sample; otherwise it stays experimental.
    """
    X, y, feature_names, groups = _build_training_data()

    if X is None or len(X) < 20:
        n = 0 if X is None else len(X)
        return {
            "status": "insufficient_data",
            "message": f"Perlu minimal 20 data poin untuk training (saat ini {n}). Tunggu lebih banyak GW selesai.",
            "n_samples": n,
        }

    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GroupKFold, cross_val_score

    n_samples = len(X)
    n_gws = len(set(int(g) for g in groups))
    if n_gws >= 2:
        cv = GroupKFold(n_splits=min(5, n_gws))
        cv_kwargs = {"groups": groups}
        split_groups = groups
    else:
        from sklearn.model_selection import KFold

        cv = KFold(n_splits=2, shuffle=True, random_state=42)
        cv_kwargs = {}
        split_groups = None

    ridge = Ridge(alpha=1.0)
    ridge_cv = cross_val_score(
        ridge, X, y, cv=cv, **cv_kwargs,
        scoring="neg_mean_absolute_error",
    )
    ridge_mae = float(-ridge_cv.mean())
    ridge.fit(X, y)

    gbr = GradientBoostingRegressor(
        n_estimators=min(150, max(30, n_samples // 15)),
        max_depth=3,
        learning_rate=0.05,
        min_samples_leaf=max(5, n_samples // 60),
        random_state=42,
    )
    gbr_cv = cross_val_score(
        gbr, X, y, cv=cv, **cv_kwargs,
        scoring="neg_mean_absolute_error",
    )
    gbr_mae = float(-gbr_cv.mean())
    gbr.fit(X, y)

    gbr_preds = gbr.predict(X)
    residuals = y - gbr_preds
    residual_std = float(np.std(residuals))

    # Formula baseline on the same held-out folds.
    proj_idx = feature_names.index("proj")
    formula_errors = []
    for _train_idx, test_idx in cv.split(X, y, split_groups):
        formula_errors.extend(np.abs(y[test_idx] - X[test_idx, proj_idx]))
    formula_mae = float(np.mean(formula_errors)) if formula_errors else float("nan")

    importances = dict(zip(feature_names, [round(float(v), 4) for v in gbr.feature_importances_]))
    improvement = (formula_mae - gbr_mae) / formula_mae * 100 if formula_mae else 0.0
    enabled = bool(
        n_samples >= 200
        and n_gws >= 4
        and math.isfinite(formula_mae)
        and gbr_mae < formula_mae
    )

    model_data = {
        "ridge": ridge,
        "gbr": gbr,
        "feature_names": feature_names,
        "residual_std": residual_std,
        "enabled": enabled,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(model_data, f)

    meta = {
        "trained_at": time.time(),
        "n_samples": n_samples,
        "n_gws": n_gws,
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "ridge_mae": round(ridge_mae, 3),
        "gbr_mae": round(gbr_mae, 3),
        "formula_mae": round(formula_mae, 3),
        "residual_std": round(residual_std, 3),
        "importances": importances,
        "improvement_vs_formula": round(improvement, 1),
        "enabled": enabled,
    }
    MODEL_META_FILE.write_text(json.dumps(meta, indent=2))

    return {
        "status": "ok",
        "n_samples": n_samples,
        "n_gws": n_gws,
        "ridge_mae": round(ridge_mae, 3),
        "gbr_mae": round(gbr_mae, 3),
        "formula_mae": round(formula_mae, 3),
        "residual_std": round(residual_std, 3),
        "improvement_pct": round(improvement, 1),
        "enabled": enabled,
        "importances": importances,
    }


def load_model():
    """Load trained ML model from file. Returns (model_data, meta) or (None, None)."""
    if not MODEL_FILE.exists() or not MODEL_META_FILE.exists():
        return None, None

    try:
        with open(MODEL_FILE, "rb") as f:
            model_data = pickle.load(f)
        meta = json.loads(MODEL_META_FILE.read_text())
        return model_data, meta
    except Exception:
        return None, None


def predict_player(player_data, model_data=None):
    """Predict expected points for a player using the ML model.

    Args:
        player_data: dict with player fields
        model_data: loaded model data (from load_model), or None to auto-load

    Returns: dict with ml_proj, ml_lower, ml_upper, or None if model not available
    """
    if model_data is None:
        model_data, _ = load_model()

    if model_data is None:
        return None
    if model_data.get("enabled") is False:
        return None

    feature_names = model_data.get("feature_names") or []
    if not feature_names:
        return None
    features = _build_prediction_features(player_data, feature_names)
    if features is None:
        return None

    try:
        gbr = model_data["gbr"]
        residual_std = model_data.get("residual_std", 2.0)

        pred = float(gbr.predict(features)[0])
        pred = max(pred, 0.0)  # No negative predictions

        # 90% confidence interval
        lower = max(pred - 1.645 * residual_std, 0.0)
        upper = pred + 1.645 * residual_std

        return {
            "ml_proj": round(pred, 2),
            "ml_lower": round(lower, 2),
            "ml_upper": round(upper, 2),
        }
    except Exception:
        return None


def predict_batch(df, model_data=None):
    """Predict ML projections for all players in a DataFrame.

    Adds columns: ml_proj, ml_lower, ml_upper

    Returns: modified DataFrame
    """
    if model_data is None:
        model_data, _ = load_model()

    ml_projs = []
    ml_lowers = []
    ml_uppers = []

    for _, row in df.iterrows():
        result = predict_player(row.to_dict(), model_data)
        if result:
            ml_projs.append(result["ml_proj"])
            ml_lowers.append(result["ml_lower"])
            ml_uppers.append(result["ml_upper"])
        else:
            ml_projs.append(None)
            ml_lowers.append(None)
            ml_uppers.append(None)

    df = df.copy()
    df["ml_proj"] = ml_projs
    df["ml_lower"] = ml_lowers
    df["ml_upper"] = ml_uppers

    return df


def model_status():
    """Check ML model status.

    Returns dict with availability, training info, etc.
    """
    _, meta = load_model()
    if meta is None:
        return {
            "available": False,
            "message": "Model ML belum di-train. Klik tombol 'Train ML Model' di halaman Akurasi.",
        }

    return {
        "available": True,
        "enabled": bool(meta.get("enabled", False)),
        "trained_at": meta.get("trained_at"),
        "n_samples": meta.get("n_samples"),
        "n_gws": meta.get("n_gws"),
        "n_features": meta.get("n_features"),
        "gbr_mae": meta.get("gbr_mae"),
        "formula_mae": meta.get("formula_mae"),
        "improvement_pct": meta.get("improvement_vs_formula"),
        "importances": meta.get("importances", {}),
    }
