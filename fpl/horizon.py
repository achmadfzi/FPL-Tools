import pandas as pd

from .availability import chance_factor
from .optimizer import best_xi
from .utils import (
    BONUS_BASELINE,
    CREATIVITY_NORM_FACTOR,
    CS_POINTS,
    CS_WEIGHT_BY_POS,
    DC_POINTS,
    GC_PENALTY_RATE,
    ICT_BASELINE,
    SAVES_NORM_FACTOR,
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


def future_proj(row, gd, event_id, steps_ahead=1):
    """Project a player's points for a future GW using current quality signals.

    Uses the SAME formula as the main projection model (model.project_player)
    so 3-GW plans stay consistent with the current-GW numbers: base signal
    from form/ppg/xGI/ICT, plus threat/bonus/creativity, DefCon bonus, CS
    bonus per fixture, dynamic fixture multipliers (teamform), minutes
    consistency & playing chance.

    `steps_ahead` (1 = the next GW after the current one, 2 = two GWs out,
    ...) applies mean reversion: hot/cold form regresses toward the player's
    season PPG, because "form" is far more fixture-driven than quality.
    """
    team = int(row["team"])
    counts = gd.team_fixture_counts(event_id)
    n = counts.get(team, 0)
    if n == 0:
        return None

    weights = _weights() or {}
    w_get = lambda k, d: (weights.get(k, d) if weights else d)  # noqa: E731

    # --- Playing chance (single source of truth: availability.py) ---
    chance = chance_factor(row, "next")
    if chance <= 0:
        return None

    # --- Early-season form confidence (mirrors model.py v3) ---
    from .model import FORM_RAMP_GWS, POS_LEAGUE_AVG, XGI_PRIOR_STRENGTH, POS_CEILING

    pos = row.get("pos", "MID")

    current_gw = gd.next_event["id"] if gd and hasattr(gd, "next_event") else 38
    starts = int(row.get("starts") or 0)
    gws_elapsed = max(current_gw - 1, 0)
    effective_gws = min(starts, gws_elapsed)
    form_confidence = min(0.2 + 0.8 * (effective_gws / FORM_RAMP_GWS), 1.0)

    pos_avg = POS_LEAGUE_AVG.get(pos, POS_LEAGUE_AVG["MID"])

    # --- Base quality signal (identical math to model.project_player v3) ---
    raw_form = float(row.get("form") or 0)
    raw_ppg = float(row.get("ppg") or 0)
    raw_xgi_per90 = float(row.get("xGI_per90") or 0)
    raw_ict_per_game = float(row.get("ict_per_game") or 0)

    # Damp form & ppg toward positional league average in early season
    form = raw_form * form_confidence + pos_avg["form"] * (1 - form_confidence)
    ppg = raw_ppg * form_confidence + pos_avg["ppg"] * (1 - form_confidence)

    # Mean reversion for future GWs: the *gap* between recent form and the
    # season PPG (a more stable quality anchor) decays with distance.
    if steps_ahead and steps_ahead > 1:
        decay = 0.75 ** (steps_ahead - 1)
        form = ppg + (form - ppg) * decay

    # Bayesian regression for xGI per 90
    minutes = float(row.get("minutes") or 0)
    sample_size_90s = max(minutes / 90.0, 0.0)
    xgi_prior = pos_avg["xgi90"]
    if sample_size_90s > 0:
        xgi_per90 = (raw_xgi_per90 * sample_size_90s + xgi_prior * XGI_PRIOR_STRENGTH) / (sample_size_90s + XGI_PRIOR_STRENGTH)
    else:
        xgi_per90 = xgi_prior

    # Damp ICT toward positional average
    ict_per_game = raw_ict_per_game * form_confidence + pos_avg["ict"] * (1 - form_confidence)

    xgi_signal = min(xgi_per90 / XGI_PER90_BASELINE, 1.0) * max(form, ppg, 2.0) if XGI_PER90_BASELINE > 0 else 0.0

    # GK saves signal — replaces xGI for goalkeepers (consistent with model.py)
    saves_per_game = float(row.get("saves_per_game") or 0)
    if pos == "GK" and saves_per_game > 0:
        saves_signal = min(saves_per_game / SAVES_NORM_FACTOR, 1.5) * max(form, ppg, 2.0)
        xgi_signal = saves_signal

    ict_signal = min(ict_per_game / ICT_BASELINE, 1.5) * max(form, ppg, 2.0) if ICT_BASELINE > 0 else 0.0

    form_w = w_get("form_w", 0.40)
    ppg_w = w_get("ppg_w", 0.20)
    xgi_w = w_get("xgi_w", 0.25)
    ict_w = w_get("ict_w", 0.15)
    base = form_w * form + ppg_w * ppg + xgi_w * xgi_signal + ict_w * ict_signal

    # --- Normalised secondary signals ---
    # Note: minutes, starts already set above for damping
    games_played = max(minutes / 90.0, 1.0) if minutes > 0 else 1.0
    threat_per_game = (float(row.get("threat") or 0)) / games_played
    threat_norm = min(threat_per_game / THREAT_NORM_FACTOR, 1.0)
    bonus_norm = min((float(row.get("bonus_per_game") or 0)) / BONUS_BASELINE, 1.5)
    creativity_norm = min((float(row.get("creativity_per_game") or 0)) / CREATIVITY_NORM_FACTOR, 1.0)

    threat_w = w_get("threat_weight", 0.08)
    bonus_w = w_get("bonus_weight", 0.08)
    creativity_w = w_get("creativity_weight", 0.06)
    cs_w = w_get("cs_weight", 0.15)

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
        cs_w_default = CS_WEIGHT_BY_POS.get(pos, 0.15)
        cs_w = w_get("cs_weight_" + pos.lower(), w_get("cs_weight", cs_w_default))
        cs_bonus = cs_prob * cs_pts * cs_w

        # Goals conceded penalty for DEF/GK (consistent with model.py)
        gc_penalty = 0.0
        if pos in ("GK", "DEF"):
            exp_gc = gd.expected_goals_conceded(team, opponent, is_home)
            gc_penalty = exp_gc * GC_PENALTY_RATE * 0.15

        # DefCon expected points (per fixture, consistent with model.py)
        dc_prob = 0.0
        if pos != "GK":
            try:
                dc_prob = float(row.get("dc_prob") or 0)
            except (TypeError, ValueError):
                dc_prob = 0.0
        dc_w = w_get("dc_weight", 0.90)
        dc_bonus = dc_prob * DC_POINTS * dc_w

        base_adj = (base + cs_bonus + threat_norm * threat_w
                    + bonus_norm * bonus_w + creativity_norm * creativity_w
                    + dc_bonus - gc_penalty)

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

    # --- Ceiling cap (consistent with model.py v3) ---
    ceiling = POS_CEILING.get(pos, 14) * len(fixtures)
    total = min(total, ceiling)

    return round(total, 2)


def horizon_df(gd, df, horizon=3):
    out = df.copy()
    cur = gd.next_event["id"]
    for i in range(horizon):
        gw = cur + i
        if i == 0:
            out[f"p{i}"] = out["proj"]
        else:
            out[f"p{i}"] = [future_proj(r, gd, gw, steps_ahead=i) for _, r in df.iterrows()]
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
