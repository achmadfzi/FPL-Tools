import random
from collections import Counter
from itertools import combinations

from .solver import best_entry, dp_select

NEED = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
BUDGET = 1000


def validate_squad(squad):
    errors = []
    if len(squad) != 15:
        errors.append(f"jumlah {len(squad)}/15")
    for pos, n in NEED.items():
        cnt = sum(1 for p in squad if p["pos"] == pos)
        if cnt != n:
            errors.append(f"{pos} {cnt}/{n}")
    clubs = Counter(p["team"] for p in squad)
    for club, cnt in clubs.items():
        if cnt > 3:
            errors.append(f"klub {club} {cnt} pemain")
    cost = sum(p["price"] for p in squad)
    if cost > BUDGET:
        errors.append(f"budget {cost / 10:.1f}m")
    return errors


def greedy_team(players, key_fn, forced=None):
    squad = list(forced or [])
    counts = Counter(p["pos"] for p in squad)
    clubs = Counter(p["team"] for p in squad)
    cost = sum(p["price"] for p in squad)
    squad_ids = {p["id"] for p in squad}
    remaining = [p for p in sorted(players, key=key_fn, reverse=True) if p["id"] not in squad_ids]
    for p in remaining:
        if counts[p["pos"]] >= NEED[p["pos"]]:
            continue
        if cost + p["price"] > BUDGET:
            continue
        if clubs[p["team"]] >= 3:
            continue
        squad.append(p)
        counts[p["pos"]] += 1
        clubs[p["team"]] += 1
        cost += p["price"]
        if len(squad) == 15:
            break
    if len(squad) < 15:
        by_pos = {pos: [p for p in players if p["pos"] == pos and p["id"] not in squad_ids] for pos in NEED}
        for pos, need in sorted(NEED.items(), key=lambda kv: kv[1]):
            while counts[pos] < need:
                cheapest = [p for p in by_pos[pos] if cost + p["price"] <= BUDGET and clubs[p["team"]] < 3]
                if not cheapest:
                    break
                p = min(cheapest, key=lambda p: p["price"])
                squad.append(p)
                counts[pos] += 1
                clubs[p["team"]] += 1
                cost += p["price"]
                squad_ids.add(p["id"])
                by_pos[pos].remove(p)
    return squad


def random_valid_squad(rng, by_pos, budget=BUDGET):
    for _ in range(400):
        squad = []
        cost = 0
        clubs = Counter()
        ok = True
        for pos, k in NEED.items():
            pool = [p for p in by_pos[pos] if clubs[p["team"]] < 3 and cost + p["price"] <= budget]
            if len(pool) < k:
                ok = False
                break
            picks = rng.sample(pool, k)
            for p in picks:
                squad.append(p)
                cost += p["price"]
                clubs[p["team"]] += 1
        if ok and len(squad) == 15:
            return squad
    return None


def random_squads(players, n=300, seed=42):
    rng = random.Random(seed)
    by_pos = {pos: [p for p in players if p["pos"] == pos and p["proj"] > 0] for pos in NEED}
    totals = []
    for _ in range(n):
        s = random_valid_squad(rng, by_pos)
        if s:
            totals.append(round(sum(p["proj"] for p in s), 2))
    return totals


def heuristic_teams(players):
    players = [p for p in players if p["proj"] and p["proj"] > 0]
    teams = {}
    keys = {
        "Kepemilikan % tertinggi": lambda p: p["selected_by"],
        "PPG musim tertinggi": lambda p: p["ppg"],
        "Proyeksi resmi FPL": lambda p: p["ep_next_fpl"],
        "Form (5 GW) tertinggi": lambda p: p["form"],
    }
    for name, key in keys.items():
        squad = greedy_team(players, key)
        teams[name] = {"total": round(sum(p["proj"] for p in squad), 2), "squad": squad}
    haaland = next((p for p in players if p["web_name"].lower() == "haaland"), None)
    saka = next((p for p in players if p["web_name"].lower() == "saka"), None)
    forced = [p for p in (haaland, saka) if p is not None and p["pos"] in ("FWD", "MID")]
    squad = greedy_team(players, lambda p: p["proj"], forced=forced)
    teams["Premium (Haaland + Saka)"] = {"total": round(sum(p["proj"] for p in squad), 2), "squad": squad}
    return teams


def brute_force(gks, defs, mids, fwds, budget=BUDGET):
    best = None
    for gk in combinations(gks, 2):
        gk_cost = gk[0]["price"] + gk[1]["price"]
        if gk_cost > budget:
            continue
        for d5 in combinations(defs, 5):
            d_cost = sum(x["price"] for x in d5)
            for m5 in combinations(mids, 5):
                m_cost = sum(x["price"] for x in m5)
                for f3 in combinations(fwds, 3):
                    if gk_cost + d_cost + m_cost + sum(x["price"] for x in f3) > budget:
                        continue
                    total = round(gk[0]["proj"] + gk[1]["proj"] + sum(x["proj"] for x in d5) + sum(x["proj"] for x in m5) + sum(x["proj"] for x in f3), 2)
                    if best is None or total > best[0]:
                        best = (total, tuple(x["id"] for x in gk + d5 + m5 + f3))
    return best


def solve_dp(gks, defs, mids, fwds, budget=BUDGET):
    cands = defs + mids + fwds
    best = None
    for gk in combinations(gks, 2):
        gk_cost = gk[0]["price"] + gk[1]["price"]
        if gk_cost > budget:
            continue
        entries = dp_select(cands, [], budget)
        entry = best_entry(entries, budget - gk_cost)
        if entry is None:
            continue
        total = round(gk[0]["proj"] + gk[1]["proj"] + entry["proj"], 2)
        if best is None or total > best[0]:
            best = (total, tuple(entry["path"]))
    return best


def dp_vs_bruteforce(df, subsets=5, seed=11):
    rng = random.Random(seed)
    pools = {
        "GK": df[(df["pos"] == "GK")].dropna(subset=["proj"]).sort_values("proj", ascending=False).head(15).to_dict("records"),
        "DEF": df[(df["pos"] == "DEF")].dropna(subset=["proj"]).sort_values("proj", ascending=False).head(25).to_dict("records"),
        "MID": df[(df["pos"] == "MID")].dropna(subset=["proj"]).sort_values("proj", ascending=False).head(25).to_dict("records"),
        "FWD": df[(df["pos"] == "FWD")].dropna(subset=["proj"]).sort_values("proj", ascending=False).head(15).to_dict("records"),
    }
    matched = 0
    details = []
    for _ in range(subsets):
        gks = rng.sample(pools["GK"], 6)
        defs = rng.sample(pools["DEF"], 8)
        mids = rng.sample(pools["MID"], 8)
        fwds = rng.sample(pools["FWD"], 6)
        bf = brute_force(gks, defs, mids, fwds)
        dp = solve_dp(gks, defs, mids, fwds)
        same = bf is not None and dp is not None and abs(bf[0] - dp[0]) < 1e-9
        matched += same
        details.append((same, dp[0] if dp else None, bf[0] if bf else None))
    return matched, subsets, details
