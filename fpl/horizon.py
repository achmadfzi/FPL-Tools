import pandas as pd

from .optimizer import best_xi
from .utils import FDR_MULT


def future_proj(row, gd, event_id):
    team = int(row["team"])
    counts = gd.team_fixture_counts(event_id)
    n = counts.get(team, 0)
    if n == 0:
        return None
    base = 0.6 * float(row["form"] or 0) + 0.4 * float(row["ppg"] or 0)
    if base <= 0:
        base = float(row["ep_next_fpl"] or 0)
    if base <= 0:
        base = float(row["proj"] or 0)
    if base <= 0:
        return None
    fx = gd.fixture_for_team_event(team, event_id)
    if fx is None:
        return None
    mult = FDR_MULT.get(fx["difficulty"], 1.0)
    mult *= 1.08 if fx["is_home"] else 0.93
    if n == 2:
        mult *= 1.9
    chance = row.get("chance")
    if chance is not None:
        mult *= max(float(chance), 0.0)
    return round(base * mult, 2)


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
