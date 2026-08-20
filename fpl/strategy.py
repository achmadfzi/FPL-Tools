from .utils import fmt_price


def gw_summary(gd, event_id):
    counts = gd.team_fixture_counts(event_id)
    fixtures = gd.fixtures_by_event_map().get(event_id, [])
    dgw_ids = [t for t, c in counts.items() if c == 2]
    bgw_ids = [t for t, c in counts.items() if c == 0]
    easy = sum(1 for f in fixtures if min(f["team_h_difficulty"], f["team_a_difficulty"]) <= 2)
    hard = sum(1 for f in fixtures if max(f["team_h_difficulty"], f["team_a_difficulty"]) >= 5)
    return {"event": event_id, "dgw_ids": dgw_ids, "bgw_ids": bgw_ids, "easy": easy, "hard": hard}


def calendar(gd, max_gws=12):
    ev = gd.next_event["id"]
    out = []
    for e in sorted(gd.events, key=lambda e: e["id"]):
        if e["id"] < ev or e.get("finished"):
            continue
        out.append(gw_summary(gd, e["id"]))
        if len(out) >= max_gws:
            break
    return out


def best_player_per_team(df):
    out = {}
    for _, r in df.dropna(subset=["proj"]).iterrows():
        t = int(r["team"])
        if t not in out or r["proj"] > out[t]["proj"]:
            out[t] = r
    return out


def tc_estimate(gw, best_per_team):
    if gw["dgw_ids"]:
        cands = [best_per_team[t] for t in gw["dgw_ids"] if t in best_per_team]
        if cands:
            b = max(cands, key=lambda p: p["proj"])
            return {
                "score": round(b["proj"] * 1.9, 2),
                "player": b["web_name"],
                "team_short": b["team_short"],
                "proj": b["proj"],
                "dgw": True,
            }
    if not best_per_team:
        return None
    b = max(best_per_team.values(), key=lambda p: p["proj"])
    factor = round(1.0 + (gw["easy"] - 5) * 0.04, 2)
    return {
        "score": round(b["proj"] * factor, 2),
        "player": b["web_name"],
        "team_short": b["team_short"],
        "proj": b["proj"],
        "dgw": False,
        "factor": factor,
    }


def bb_estimate(gw, squad):
    if not squad:
        return None
    vals = [(p, 1.8 if int(p["team"]) in gw["dgw_ids"] else 1.0) for p in squad]
    vals.sort(key=lambda x: x[0]["proj"] * x[1])
    bench = sum(p["proj"] * m for p, m in vals[:4])
    dgw_count = sum(1 for p in squad if int(p["team"]) in gw["dgw_ids"])
    return {"score": round(bench, 2), "dgw_count": dgw_count}


def bench_players(squad):
    vals = sorted(squad, key=lambda p: p["proj"])
    return vals[:4]


def squad_from_ids(df, squad_ids):
    by_id = {p["id"]: p for p in df.to_dict("records")}
    out = []
    for i in squad_ids:
        p = by_id.get(i)
        if p is None:
            continue
        out.append(
            {
                "id": p["id"],
                "web_name": p["web_name"],
                "team_short": p["team_short"],
                "team": int(p["team"]),
                "pos": p["pos"],
                "price": p["price"],
                "proj": p["proj"] if p["proj"] else 0.0,
                "photo_code": p.get("photo_code"),
            }
        )
    return out
