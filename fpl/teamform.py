"""Dynamic team strength indices & calibrated CS probability.

FPL's static `strength_*` ratings are often 0 at the start of the season and,
later, do not reflect in-season form. This module derives rolling attack /
goals-conceded indices from actual finished fixtures (already cached from the
fixtures endpoint) smoothed toward the league average, then uses them to:

- adjust the per-fixture points multiplier around the FDR baseline, and
- estimate clean-sheet probability via an exp(-lambda) model calibrated to
  observed clean-sheet rates per context (home/away).

All outputs are centered so that an average team maps to index 1.0 / ratio 1.0,
meaning the module acts as a *correction* around the existing FDR logic and
degrades gracefully to FDR-only behaviour on missing data.
"""

import math


# Weight of actuals: w = played / (played + SMOOTH_K). Small k = more responsive.
SMOOTH_K = 1.5
# Cap how much of the final signal can come from actuals (stops overreaction
# to a 1-2 game hot/cold streak early in the season).
MAX_ACTUAL_W = 0.75
# Early-season ramp: require at least this many team matches before actuals
# contribute at all.
MIN_MATCHES = 2

# Exponent applied to the scoring ratio for the fixture multiplier.
# ratio 1.5  -> dyn ~1.15 ; ratio 0.66 -> dyn ~0.87
MULT_EXP = 0.35
DYN_CLAMP = (0.80, 1.20)


def build_team_indices(gd):
    """Compute rolling attack / goals-conceded indices from finished fixtures.

    Returns:
        dict: {team_id: {"att": float, "gc": float, "played": int, "w": float}}
              plus meta attached under key "_meta". Indices are centred on 1.0
              (1.0 == league average). "gc" > 1.0 means the team concedes MORE
              than average (i.e. worse defence); "att" > 1.0 attacks more.
        Returns {} (and a healthy default for every call site) when no
        finished fixtures exist.
    """
    teams = gd.teams_by_id
    acc = {tid: {"gf": 0, "ga": 0, "m": 0} for tid in teams}

    finished = [f for f in gd.fixtures
                if (f.get("finished") or f.get("finished_provisional"))
                and f.get("team_h_score") is not None
                and f.get("team_a_score") is not None]
    if not finished:
        return {}

    home_cs_matches = 0
    away_cs_matches = 0
    home_cs = 0  # home team kept a clean sheet
    away_cs = 0  # away team kept a clean sheet

    for f in finished:
        h, a = f["team_h"], f["team_a"]
        gh, ga = f["team_h_score"], f["team_a_score"]
        acc[h]["gf"] += gh
        acc[h]["ga"] += ga
        acc[h]["m"] += 1
        acc[a]["gf"] += ga
        acc[a]["ga"] += gh
        acc[a]["m"] += 1
        home_cs_matches += 1
        away_cs_matches += 1
        if ga == 0:
            home_cs += 1
        if gh == 0:
            away_cs += 1

    n_matches = len(finished)
    total_gf = sum(v["gf"] for v in acc.values())
    L_overall = total_gf / (2.0 * n_matches) if n_matches else 0.0
    L_home = sum(f["team_h_score"] for f in finished) / n_matches if n_matches else 1.4
    L_away = sum(f["team_a_score"] for f in finished) / n_matches if n_matches else 1.2

    # Observed CS rates by "conceding side" context.
    cs_home_rate = home_cs / max(home_cs_matches, 1)   # T home conceding vs away opponent
    cs_away_rate = away_cs / max(away_cs_matches, 1)   # T away conceding vs home opponent

    # Smoothed rates (towards league mean) then normalised so mean == 1.
    gf_rates, ga_rates = {}, {}
    for tid, v in acc.items():
        played = v["m"]
        gf_rate = (v["gf"] + SMOOTH_K * L_overall) / (played + SMOOTH_K) if played else 1.0
        ga_rate = (v["ga"] + SMOOTH_K * L_overall) / (played + SMOOTH_K) if played else 1.0
        gf_rates[tid] = gf_rate
        ga_rates[tid] = ga_rate

    mean_gf = sum(gf_rates.values()) / max(len(gf_rates), 1)
    mean_ga = sum(ga_rates.values()) / max(len(ga_rates), 1)

    out = {}
    for tid, v in acc.items():
        played = v["m"]
        att = (gf_rates[tid] / mean_gf) if mean_gf else 1.0
        gc = (ga_rates[tid] / mean_ga) if mean_ga else 1.0
        w = min(MAX_ACTUAL_W, played / (played + SMOOTH_K)) if played else 0.0
        out[tid] = {"att": round(att, 4), "gc": round(gc, 4),
                    "played": played, "w": round(w, 4)}

    out["_meta"] = {
        "n_matches": n_matches,
        "L_home": round(L_home, 4),
        "L_away": round(L_away, 4),
        "L_overall": round(L_overall, 4),
        "cs_home_rate": round(cs_home_rate, 4),
        "cs_away_rate": round(cs_away_rate, 4),
        "min_matches": MIN_MATCHES,
    }
    return out


def _scoring_ratio(indices, tid, oid):
    """Predicted goals for `tid` vs `oid` relative to the league average."""
    t = indices.get(tid, {})
    o = indices.get(oid, {})
    att = t.get("att") if isinstance(t.get("att"), (int, float)) and t.get("att", 0) > 0 else 1.0
    gc = o.get("gc") if isinstance(o.get("gc"), (int, float)) and o.get("gc", 0) > 0 else 1.0
    return att * gc


def fixture_dyn_mult(gd, indices, team_id, opponent_id, is_home):
    """Multiplier adjustment around the FDR baseline for this fixture.

    Returns a factor centred on 1.0 that the caller multiplies with the
    (possibly tuned) FDR multiplier. Returns 1.0 when actual data is too
    sparse to be trusted (early season).
    """
    t = indices.get(team_id, {})
    o = indices.get(opponent_id, {})
    if not t or not o:
        return 1.0
    if int(t.get("played", 0)) < MIN_MATCHES or int(o.get("played", 0)) < MIN_MATCHES:
        return 1.0
    ratio = _scoring_ratio(indices, team_id, opponent_id)
    dyn = math.exp(MULT_EXP * math.log(ratio)) if ratio > 0 else 1.0
    dyn = max(DYN_CLAMP[0], min(DYN_CLAMP[1], dyn))
    w = min(float(t.get("w", 0.0)), float(o.get("w", 0.0)))
    return round(1.0 + w * (dyn - 1.0), 4)


def cs_probability(gd, indices, team_id, opponent_id, is_home, fdr=None):
    """Clean-sheet probability for `team_id` vs `opponent_id`.

    Model: p(CS) = exp(-expected_goals_conceded * scale), where the scale is
    calibrated per "scoring context" to the observed league CS rate, then
    blended (by actual-data weight) with the old FDR-based prior so behaviour
    degrades gracefully early in the season.
    """
    # FDR-based prior (old behaviour — robust fallback).
    fdr_cs = {1: 0.40, 2: 0.35, 3: 0.28, 4: 0.20, 5: 0.15}
    base = fdr_cs.get(fdr, 0.28) if fdr is not None else 0.28
    prior = max(0.05, min(0.55, base + (0.05 if is_home else 0.0)))

    meta = indices.get("_meta", {})
    if not meta or meta.get("n_matches", 0) < meta.get("min_matches", MIN_MATCHES):
        return prior

    t = indices.get(team_id, {})
    o = indices.get(opponent_id, {})
    if not t or not o:
        return prior
    if int(t.get("played", 0)) < MIN_MATCHES or int(o.get("played", 0)) < MIN_MATCHES:
        return prior

    # Opponent's expected goals: L_ctx * att_opp * gc_team
    if is_home:
        L = meta.get("L_away", 1.2)     # opponent is away
        scale = -math.log(max(meta.get("cs_home_rate", 0.3), 0.05)) / L if L else 0.0
    else:
        L = meta.get("L_home", 1.4)     # opponent is home
        scale = -math.log(max(meta.get("cs_away_rate", 0.25), 0.05)) / L if L else 0.0
    if scale <= 0:
        return prior

    lam = L * max(float(o.get("att") or 0.0), 0.0) * max(float(t.get("gc") or 0.0), 0.0)
    if lam <= 0:
        return prior
    dyn = math.exp(-lam * scale)
    dyn = max(0.05, min(0.60, dyn))

    w = min(float(t.get("w", 0.0)), float(o.get("w", 0.0)))
    return round(prior + w * (dyn - prior), 4)
