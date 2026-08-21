import pandas as pd

from .optimizer import best_xi
from .utils import FDR_MULT


def future_proj(row, gd, event_id):
    """Project a player's points for a future GW using current quality signals."""
    team = int(row["team"])
    counts = gd.team_fixture_counts(event_id)
    n = counts.get(team, 0)
    if n == 0:
        return None

    # Use enhanced base: form + ppg + xGI signal (from current data)
    form = float(row["form"] or 0)
    ppg = float(row["ppg"] or 0)
    xgi_signal = float(row.get("xgi_signal") or 0)
    base = 0.45 * form + 0.25 * ppg + 0.30 * xgi_signal

    if base <= 0:
        base = float(row.get("ep_next_fpl") or 0)
    if base <= 0:
        base = float(row.get("proj") or 0)
    if base <= 0:
        return None

    # Get fixture details for this future GW
    fixtures = gd.fixture_list_for_team_event(team, event_id)
    if not fixtures:
        fx = gd.fixture_for_team_event(team, event_id)
        if fx is None:
            return None
        fixtures = [fx]

    total = 0.0
    for fx in fixtures:
        mult = FDR_MULT.get(fx["difficulty"], 1.0)
        mult *= 1.08 if fx["is_home"] else 0.93

        # CS bonus for defenders/keepers
        pos = row.get("pos", "MID")
        if pos in ("GK", "DEF"):
            cs_prob = gd.cs_probability(team, fx["opponent"], fx["is_home"], fdr=fx["difficulty"])
            cs_bonus = cs_prob * 4 * 0.15
        elif pos == "MID":
            cs_prob = gd.cs_probability(team, fx["opponent"], fx["is_home"], fdr=fx["difficulty"])
            cs_bonus = cs_prob * 1 * 0.15
        else:
            cs_bonus = 0.0

        total += (base + cs_bonus) * mult

    chance = row.get("chance")
    if chance is not None:
        total *= max(float(chance), 0.0)

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
