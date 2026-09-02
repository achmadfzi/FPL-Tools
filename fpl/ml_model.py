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


def _build_training_data():
    """Build training dataset from accuracy history + player data.

    For each completed GW, we match projections with actuals AND
    try to reconstruct feature vectors from the cached player data.

    Returns: (X: np.ndarray, y: np.ndarray, feature_names: list)
    """
    from .accuracy import _load as load_accuracy

    data = load_accuracy()
    X_rows = []
    y_rows = []

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
            proj = proj_info.get("proj", 0)
            pos = proj_info.get("pos", "MID")
            fdr = proj_info.get("fdr")

            if proj is None or proj <= 0:
                continue

            # Build feature vector from available data
            # We use the projection itself and derived features
            features = {
                "proj": proj,
                "fdr": fdr if fdr is not None else 3,
                "pos_gk": 1 if pos == "GK" else 0,
                "pos_def": 1 if pos == "DEF" else 0,
                "pos_mid": 1 if pos == "MID" else 0,
                "pos_fwd": 1 if pos == "FWD" else 0,
                "proj_squared": proj ** 2,
                "proj_log": math.log(max(proj, 0.1)),
                "fdr_easy": 1 if fdr and fdr <= 2 else 0,
                "fdr_hard": 1 if fdr and fdr >= 4 else 0,
            }

            X_rows.append([features[k] for k in sorted(features.keys())])
            y_rows.append(actual)

    if not X_rows:
        return None, None, sorted(features.keys()) if X_rows else []

    return np.array(X_rows, dtype=np.float64), np.array(y_rows, dtype=np.float64), sorted(features.keys())


def _build_prediction_features(player_data):
    """Build feature vector for a single player for prediction.

    Args:
        player_data: dict with player fields (from projection table row)

    Returns: np.ndarray of shape (1, n_features)
    """
    proj = float(player_data.get("proj") or 0)
    fdr = player_data.get("fdr")
    pos = player_data.get("pos", "MID")

    if proj <= 0:
        return None

    features = {
        "fdr": fdr if fdr is not None else 3,
        "fdr_easy": 1 if fdr and fdr <= 2 else 0,
        "fdr_hard": 1 if fdr and fdr >= 4 else 0,
        "pos_def": 1 if pos == "DEF" else 0,
        "pos_fwd": 1 if pos == "FWD" else 0,
        "pos_gk": 1 if pos == "GK" else 0,
        "pos_mid": 1 if pos == "MID" else 0,
        "proj": proj,
        "proj_log": math.log(max(proj, 0.1)),
        "proj_squared": proj ** 2,
    }

    return np.array([[features[k] for k in sorted(features.keys())]], dtype=np.float64)


def train_model():
    """Train ML models on historical data.

    Trains both Ridge Regression (simple, interpretable) and
    Gradient Boosting Regressor (more accurate).

    Returns: dict with training results and metrics.
    """
    X, y, feature_names = _build_training_data()

    if X is None or len(X) < 20:
        n = 0 if X is None else len(X)
        return {
            "status": "insufficient_data",
            "message": f"Perlu minimal 20 data poin untuk training (saat ini {n}). Tunggu lebih banyak GW selesai.",
            "n_samples": n,
        }

    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import cross_val_score

    n_samples = len(X)

    # Train Ridge Regression
    ridge = Ridge(alpha=1.0)
    ridge_cv = cross_val_score(ridge, X, y, cv=min(5, n_samples), scoring="neg_mean_absolute_error")
    ridge_mae = -ridge_cv.mean()
    ridge.fit(X, y)

    # Train Gradient Boosting
    gbr = GradientBoostingRegressor(
        n_estimators=min(100, max(20, n_samples // 2)),
        max_depth=3,
        learning_rate=0.1,
        min_samples_leaf=max(2, n_samples // 20),
        random_state=42,
    )
    gbr_cv = cross_val_score(gbr, X, y, cv=min(5, n_samples), scoring="neg_mean_absolute_error")
    gbr_mae = -gbr_cv.mean()
    gbr.fit(X, y)

    # Compute residuals for confidence intervals
    gbr_preds = gbr.predict(X)
    residuals = y - gbr_preds
    residual_std = float(np.std(residuals))

    # Compute baseline MAE (just using formula projection as-is)
    proj_idx = sorted({
        "fdr": 0, "fdr_easy": 0, "fdr_hard": 0,
        "pos_def": 0, "pos_fwd": 0, "pos_gk": 0, "pos_mid": 0,
        "proj": 0, "proj_log": 0, "proj_squared": 0,
    }.keys()).index("proj")
    formula_preds = X[:, proj_idx]
    formula_mae = float(np.mean(np.abs(y - formula_preds)))

    # Feature importance from GBR
    importances = dict(zip(feature_names, [round(float(v), 4) for v in gbr.feature_importances_]))

    # Save models
    model_data = {
        "ridge": ridge,
        "gbr": gbr,
        "feature_names": feature_names,
        "residual_std": residual_std,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(model_data, f)

    # Save metadata
    meta = {
        "trained_at": time.time(),
        "n_samples": n_samples,
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "ridge_mae": round(ridge_mae, 3),
        "gbr_mae": round(gbr_mae, 3),
        "formula_mae": round(formula_mae, 3),
        "residual_std": round(residual_std, 3),
        "importances": importances,
        "improvement_vs_formula": round((formula_mae - gbr_mae) / formula_mae * 100, 1),
    }
    MODEL_META_FILE.write_text(json.dumps(meta, indent=2))

    return {
        "status": "ok",
        "n_samples": n_samples,
        "ridge_mae": round(ridge_mae, 3),
        "gbr_mae": round(gbr_mae, 3),
        "formula_mae": round(formula_mae, 3),
        "residual_std": round(residual_std, 3),
        "improvement_pct": round((formula_mae - gbr_mae) / formula_mae * 100, 1),
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

    features = _build_prediction_features(player_data)
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
        "trained_at": meta.get("trained_at"),
        "n_samples": meta.get("n_samples"),
        "gbr_mae": meta.get("gbr_mae"),
        "formula_mae": meta.get("formula_mae"),
        "improvement_pct": meta.get("improvement_vs_formula"),
        "importances": meta.get("importances", {}),
    }
