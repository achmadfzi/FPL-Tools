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


# ---------------------------------------------------------------------------
# Wildcard, Free Hit, and Chip Sequence (Prioritas 4)
# ---------------------------------------------------------------------------


def wc_estimate(gw, gd, df, squad=None):
    """Estimate the value of using Wildcard at a given GW.

    Wildcard value is high when:
    1. Many current squad players are underperforming or have bad fixtures ahead
    2. There's a big fixture swing (many teams going easy → hard or vice versa)
    3. Multiple injuries in squad

    Returns: dict with score and reasoning, or None.
    """
    counts = gd.team_fixture_counts(gw["event"])

    # Factor 1: Fixture swing — how many teams switch from hard to easy (or vice versa)
    # Look at next 3 GWs worth of easy fixtures
    future_easy = 0
    for offset in range(3):
        future_gw = gw["event"] + offset
        future_fixtures = gd.fixtures_by_event_map().get(future_gw, [])
        future_easy += sum(1 for f in future_fixtures
                          if min(f["team_h_difficulty"], f["team_a_difficulty"]) <= 2)

    # Factor 2: DGW opportunity — rebuild for DGW
    dgw_bonus = len(gw["dgw_ids"]) * 3.0

    # Factor 3: Squad underperformance (if we have a squad)
    squad_penalty = 0.0
    underperformers = []
    if squad:
        avg_proj = sum(p["proj"] for p in squad) / max(len(squad), 1)
        for p in squad:
            if p["proj"] < avg_proj * 0.5:
                squad_penalty += avg_proj - p["proj"]
                underperformers.append(p["web_name"])

    # Factor 4: How many BGW teams are in squad
    bgw_penalty = 0.0
    bgw_players = []
    if squad and gw["bgw_ids"]:
        for p in squad:
            if int(p["team"]) in gw["bgw_ids"]:
                bgw_penalty += p["proj"]
                bgw_players.append(p["web_name"])

    score = round(future_easy * 0.5 + dgw_bonus + squad_penalty * 0.3 + bgw_penalty * 0.5, 2)

    return {
        "score": score,
        "future_easy_fixtures": future_easy,
        "dgw_teams": len(gw["dgw_ids"]),
        "underperformers": underperformers[:5],
        "bgw_players": bgw_players,
        "reasoning": [],
    }


def fh_estimate(gw, gd, df):
    """Estimate the value of using Free Hit at a given GW.

    Free Hit is most valuable during Blank GWs where many teams don't play,
    allowing you to field a full team of players who ARE playing.

    Returns: dict with score and reasoning, or None.
    """
    counts = gd.team_fixture_counts(gw["event"])

    # How many teams are NOT playing?
    all_teams = set(gd.teams_by_id.keys())
    playing_teams = {t for t, c in counts.items() if c > 0}
    blank_teams = all_teams - playing_teams
    n_blank = len(blank_teams)

    if n_blank == 0:
        # Not a blank GW — Free Hit has limited value
        return {
            "score": round(gw["easy"] * 0.3, 2),
            "n_blank_teams": 0,
            "is_bgw": False,
            "best_available": None,
            "reasoning": ["Bukan Blank GW — Free Hit lebih baik disimpan untuk BGW."],
        }

    # Calculate best possible XI from playing teams only
    playing_players = df[df["team"].isin(playing_teams)].dropna(subset=["proj"])
    if len(playing_players) == 0:
        return {"score": 0, "n_blank_teams": n_blank, "is_bgw": True, "reasoning": ["Tidak ada data pemain yang bermain."]}

    # Estimate: best 11 from playing teams
    top11 = playing_players.nlargest(11, "proj")["proj"].sum()
    # vs average 11 (if you didn't use FH, some of your players wouldn't play)
    # Estimate ~3-4 of your 11 might be from blank teams
    estimated_loss = n_blank / 20.0 * 11 * 2.0  # rough estimate of lost points

    score = round(estimated_loss + gw["easy"] * 0.5, 2)

    blank_names = [gd.teams_by_id[t]["short_name"] for t in blank_teams]

    return {
        "score": score,
        "n_blank_teams": n_blank,
        "blank_teams": blank_names,
        "is_bgw": True,
        "best_11_proj": round(top11, 2),
        "reasoning": [
            f"{n_blank} tim tidak bermain: {', '.join(blank_names)}",
            f"Best XI dari tim yang bermain: {top11:.2f} poin",
        ],
    }


def chip_sequence(cal, tc_scores, bb_scores, wc_scores, fh_scores):
    """Recommend optimal sequence for using all 4 chips across the season.

    Rules:
    - Each chip can only be used once
    - TC and BB cannot be used in the same GW
    - WC and FH can be used alongside TC/BB (different GW)

    Strategy:
    1. Rank each chip's best GW
    2. Resolve conflicts (same GW)
    3. Return ordered plan

    Returns: list of {"chip": name, "gw": N, "score": X, "reason": str}
    """
    chips = {}

    # Find best GW for each chip
    if tc_scores:
        best_tc = max(tc_scores, key=lambda x: x["score"])
        chips["TC"] = best_tc
    if bb_scores:
        best_bb = max(bb_scores, key=lambda x: x["score"])
        chips["BB"] = best_bb
    if wc_scores:
        best_wc = max(wc_scores, key=lambda x: x["score"])
        chips["WC"] = best_wc
    if fh_scores:
        best_fh = max(fh_scores, key=lambda x: x["score"])
        chips["FH"] = best_fh

    # Resolve conflicts: if TC and BB want the same GW, give it to the higher scorer
    if "TC" in chips and "BB" in chips and chips["TC"]["gw"] == chips["BB"]["gw"]:
        if chips["TC"]["score"] >= chips["BB"]["score"]:
            # Move BB to second best
            remaining = [s for s in bb_scores if s["gw"] != chips["TC"]["gw"]]
            if remaining:
                chips["BB"] = max(remaining, key=lambda x: x["score"])
        else:
            remaining = [s for s in tc_scores if s["gw"] != chips["BB"]["gw"]]
            if remaining:
                chips["TC"] = max(remaining, key=lambda x: x["score"])

    plan = []
    for chip_name in ("WC", "FH", "TC", "BB"):
        if chip_name in chips:
            c = chips[chip_name]
            plan.append({
                "chip": chip_name,
                "gw": c["gw"],
                "score": c["score"],
                "reason": c.get("reason", ""),
            })

    plan.sort(key=lambda x: x["gw"])
    return plan

