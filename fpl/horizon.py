import pandas as pd

from .optimizer import best_xi
from .utils import (
    BONUS_BASELINE,
    CREATIVITY_NORM_FACTOR,
    CS_POINTS,
    ICT_BASELINE,
    THREAT_NORM_FACTOR,
    XGI_PER90_BASELINE,
)


def _weights():
    """Active (tuned if available) model weights — consistent with model.py."""
    try:
        from .adaptive import get_active_weights

        return get_active_weights()
    except Exception:
        return None


def future_proj(row, gd, event_id):
    """Project a player's points for a future GW using current quality signals.

    Uses the SAME formula as the main projection model (model.project_player)
    so 3-GW plans stay consistent with the current-GW numbers: base signal
    from form/ppg/xGI/ICT, plus threat/bonus/creativity, CS bonus per fixture,
    dynamic fixture multipliers (teamform), minutes consistency & playing chance.
    """
    team = int(row["team"])
    counts = gd.team_fixture_counts(event_id)
    n = counts.get(team, 0)
    if n == 0:
        return None

    weights = _weights() or {}
    w_get = lambda k, d: (weights.get(k, d) if weights else d)  # noqa: E731

    # --- Playing chance ---
    chance = row.get("chance")
    if chance is None or pd.isna(chance):
        chance = 1.0
    else:
        chance = max(float(chance) / 100.0, 0.0)
    if chance <= 0:
        return None
    if row.get("status") in ("i", "u", "n") and chance < 0.5:
        return None

    # --- Base quality signal (identical math to model.project_player) ---
    form = float(row.get("form") or 0)
    ppg = float(row.get("ppg") or 0)
    xgi_per90 = float(row.get("xGI_per90") or 0)
    xgi_signal = min(xgi_per90 / XGI_PER90_BASELINE, 1.0) * max(form, ppg, 2.0) if XGI_PER90_BASELINE > 0 else 0.0
    ict_per_game = float(row.get("ict_per_game") or 0)
    ict_signal = min(ict_per_game / ICT_BASELINE, 1.5) * max(form, ppg, 2.0) if ICT_BASELINE > 0 else 0.0

    form_w = w_get("form_w", 0.40)
    ppg_w = w_get("ppg_w", 0.20)
    xgi_w = w_get("xgi_w", 0.25)
    ict_w = w_get("ict_w", 0.15)
    base = form_w * form + ppg_w * ppg + xgi_w * xgi_signal + ict_w * ict_signal

    # --- Normalised secondary signals ---
    minutes = float(row.get("minutes") or 0)
    starts = int(row.get("starts") or 0)
    games_played = max(minutes / 90.0, 1.0) if minutes > 0 else 1.0
    threat_per_game = (float(row.get("threat") or 0)) / games_played
    threat_norm = min(threat_per_game / THREAT_NORM_FACTOR, 1.0)
    bonus_norm = min((float(row.get("bonus_per_game") or 0)) / BONUS_BASELINE, 1.5)
    creativity_norm = min((float(row.get("creativity_per_game") or 0)) / CREATIVITY_NORM_FACTOR, 1.0)

    threat_w = w_get("threat_weight", 0.08)
    bonus_w = w_get("bonus_weight", 0.08)
    creativity_w = w_get("creativity_weight", 0.06)
    cs_w = w_get("cs_weight", 0.15)
    pos = row.get("pos", "MID")

    # Minutes consistency (same as model.py)
    if starts == 0 or minutes == 0:
        minutes_factor = 0.85
    else:
        mps = minutes / max(starts, 1)
        minutes_factor = 1.0 if mps >= 85 else 0.95 if mps >= 75 else 0.88 if mps >= 60 else 0.78 if mps >= 45 else 0.65

    # --- Fixtures for this future event ---
    fixtures = gd.fixture_list_for_team_event(team, event_id)
    if not fixtures:
        fx = gd.fixture_for_team_event(team, event_id)
        if fx is None:
            return None
        fixtures = [fx]

    total = 0.0
    for fx in fixtures:
        is_home = fx["is_home"]
        fdr = fx["difficulty"]
        opponent = fx["opponent"]
        home_mult = 1.08 if is_home else 0.93

        cs_prob = gd.cs_probability(team, opponent, is_home, fdr=fdr)
        cs_pts = CS_POINTS.get(pos, 0)
        cs_bonus = cs_prob * cs_pts * cs_w

        base_adj = (base + cs_bonus + threat_norm * threat_w
                    + bonus_norm * bonus_w + creativity_norm * creativity_w)

        # FDR multiplier (possibly tuned) × dynamic rolling-strength correction
        try:
            from .adaptive import DEFAULT_WEIGHTS

            active_fdr = weights.get("fdr_mult", DEFAULT_WEIGHTS["fdr_mult"]) if weights else None
        except Exception:
            active_fdr = None
        if isinstance(active_fdr, dict):
            fdr_mult = active_fdr.get(fdr, active_fdr.get(str(fdr), 1.0))
        else:
            fdr_mult = 1.0
        dyn_mult = gd.fixture_dyn_mult(team, opponent, is_home)
        total += (base_adj * fdr_mult * dyn_mult * home_mult) if base > 0 else 0.0

    if base <= 0:
        # No form/ppg data — fall back to FPL's ep_next (scaled for DGW)
        ep = float(row.get("ep_next_fpl") or row.get("ep_next") or 0)
        total = ep * (1.8 if len(fixtures) > 1 else 1.0)
    if total <= 0:
        return None

    total *= minutes_factor * chance
    return round(total, 2)


def horizon_df(gd, df, horizon=3):
    out = df.copy()
    cur = gd.next_event["id"]
    for i in range(horizon):
        gw = cur + i
        if i == 0:
            out[f"p{i}"] = out["proj"]
        else:
            out[f"p{i}"] = [future_proj(r, gd, gw) for _, r in df.iterrows()]
    out["horizon"] = out[[f"p{i}" for i in range(horizon)]].sum(axis=1)
    return out


def player_gw_projections(df, gd, horizon=3):
    hdf = horizon_df(gd, df, horizon)
    out = {}
    for _, r in hdf.iterrows():
        vals = []
        for i in range(horizon):
            v = r.get(f"p{i}")
            vals.append(float(v) if pd.notna(v) else 0.0)
        out[int(r["id"])] = vals
    return out


def squad_plan(squad, gw_projs, horizon=3):
    plans = []
    for i in range(horizon):
        tmp = [{**p, "proj": gw_projs.get(p["id"], [0.0] * horizon)[i]} for p in squad]
        plans.append(best_xi(tmp))
    return plans


def risky_players(squad, gw_projs, horizon=3):
    scored = []
    for p in squad:
        future = sum(gw_projs.get(p["id"], [0.0] * horizon)[1:])
        scored.append((p, round(future, 2)))
    scored.sort(key=lambda x: x[1])
    return scored[:3]
