"""Monte-Carlo Gameweek simulator & captain/vice-captain analysis.

Why: point estimates alone cannot answer "is the top pick also the best
*captain*?" or "should I pick a safer vice-captain?". This module samples many
possible outcomes of the upcoming Gameweek (goals via Poisson from dynamic
team strengths, goal/assist allocation via xG-based shares, clean sheets,
appearances/minutes, bonus proxy) and derives distributions instead of single
numbers.

Design notes (approximation on purpose):
- match goals:       Poisson(lambda) with lambda from dynamic teamform indices
- goal allocation:   weighted draws among the whole team roster using each
                     player's xGI/90 x expected-minutes share
- assist allocation: for every goal, 72% chance of an assist drawn from the
                     scorer's team-mates (self-assist excluded)
- minutes:           drawn around the player's expected minutes (player_history
                     when available, else season minutes-per-start proxy)
- clean sheet:       +4/+4/+1 for GK/DEF/MID that played >= 60 mins
- bonus:             top-3 weighted draw over both teams of the match, weights
                     = season bonus tendency boosted by events (goals/assists/CS)
- captain:           EV = 2x pts if C plays, else 2x pts of the vice-captain
                     if VC plays, else 0 (auto-sub replacement is not doubled)

Deterministic by default (fixed seed) so results are reproducible.
"""

import math

import numpy as np
from collections import Counter

from .utils import CS_POINTS

GOAL_PTS = {"GK": 6, "DEF": 6, "MID": 5, "FWD": 4}
ASSIST_PTS = 3
MIN_MINS_FULL = 60
P_ASSIST = 0.72
N_BONUS = 3


def _chance(row):
    c = row.get("chance")
    try:
        if c is None or (isinstance(c, float) and math.isnan(c)):
            return 1.0
        return max(0.0, min(1.0, float(c) / 100.0))
    except (TypeError, ValueError):
        return 1.0


def minutes_proxy(row):
    """Expected minutes for the match (0..90)."""
    em = row.get("exp_minutes")
    try:
        if em and float(em) > 0:
            return min(90.0, float(em))
    except (TypeError, ValueError):
        pass
    minutes = float(row.get("minutes") or 0)
    starts = int(row.get("starts") or 0)
    if starts > 0:
        return min(90.0, minutes / max(starts, 1))
    if minutes > 0:
        return 30.0
    return 0.0


def _attack_weight(row):
    xgi = float(row.get("xGI_per90") or 0)
    return xgi * (minutes_proxy(row) / 90.0) * _chance(row)


def _pos_points(pos, goals):
    return GOAL_PTS.get(pos, 5) * goals


def _sample_minutes(rng, row):
    """Sample actual minutes for one match (0 means not playing)."""
    p = _chance(row)
    if p <= 0:
        return 0
    if rng.random() > p:
        return 0
    base = minutes_proxy(row)
    if base <= 0:
        return 0
    m = base + float(rng.normal(0.0, 6.0))
    m = max(0.0, min(90.0, m))
    if m < 12 and rng.random() < 0.85:
        return 0
    return round(m)


def _rosters(gd, df):
    """Per-team roster: attack weights + bonus tendencies, keyed by player id."""
    teams = {}
    for _, r in df.iterrows():
        tid = int(r["team"])
        pid = int(r["id"])
        entry = teams.setdefault(tid, {"rows": {}, "pos": {}, "w": {}, "tend": {}})
        entry["rows"][pid] = r
        entry["pos"][pid] = r.get("pos", "MID")
        tend = float(r.get("bonus_per_game") or 0)
        entry["tend"][pid] = tend if tend > 0 else 0.02
        entry["w"][pid] = _attack_weight(r)
    return teams


def _goals_lambda(gd, team_id, opp_id, is_home):
    ti = getattr(gd, "team_indices", None)
    meta = (ti or {}).get("_meta", {}) if ti else {}
    if ti:
        t = ti.get(team_id, {}) or {}
        o = ti.get(opp_id, {}) or {}
        att = float(t.get("att") or 1.0) if float(t.get("att") or 0) > 0 else 1.0
        gc = float(o.get("gc") or 1.0) if float(o.get("gc") or 0) > 0 else 1.0
    else:
        att, gc = 1.0, 1.0
    L = meta.get("L_home" if is_home else "L_away", 1.4 if is_home else 1.2)
    return max(0.05, L * att * gc)


def simulate_gw(gd, df, squad_rows, n=600, seed=42):
    """Simulate the upcoming Gameweek for a subset of players.

    Args:
        gd: GameData
        df: full projection table (rosters are taken from here)
        squad_rows: list of projection rows whose points we record
        n: number of iterations
        seed: random seed

    Returns:
        (pts, played): {player_id: [n values]} — points (no captain doubling)
        and {player_id: [n bools]} — played at all.
    """
    squad_rows = list(squad_rows)
    involved = {}
    for r in squad_rows:
        involved.setdefault(int(r["team"]), {})[int(r["id"])] = r
    all_pids = [pid for tm in involved.values() for pid in tm]
    teams = _rosters(gd, df)
    rng = np.random.default_rng(seed)

    fmap = {tid: gd.fixture_list_for_team(tid) for tid in involved}
    pair_keys = {}
    for tid, fxs in fmap.items():
        for fx in fxs:
            oid = fx["opponent"]
            key = (min(tid, oid), max(tid, oid))
            pair_keys.setdefault(key, []).append((tid, oid, fx["is_home"]))

    pts = {pid: [0.0] * n for pid in all_pids}
    played = {pid: [False] * n for pid in all_pids}

    for it in range(n):
        for (h, a), entries in pair_keys.items():
            home_entry = [e for e in entries if e[2]]
            away_entry = [e for e in entries if not e[2]]
            gh = _goals_lambda(gd, h, a, True) if home_entry else 0.0
            ga = _goals_lambda(gd, a, h, False) if away_entry else 0.0
            g_home = int(rng.poisson(lam=gh)) if gh > 0 else 0
            g_away = int(rng.poisson(lam=ga)) if ga > 0 else 0

            sides = []
            if home_entry:
                sides.append((h, a, True, g_home, g_away))
            if away_entry:
                sides.append((a, h, False, g_away, g_home))

            # ---- per side: minutes, CS, allocation, events ----
            side_stats = []
            for tid, oid, is_home, scored, conceded in sides:
                tgt = involved.get(tid)
                if not tgt:
                    continue
                rt = teams[tid]
                # 1) minutes for every involved player of this team
                mins_t = {}
                for pid, row in tgt.items():
                    m = _sample_minutes(rng, row)
                    mins_t[pid] = m
                    played[pid][it] = m > 0
                # 2) clean sheet markers
                cs_t = {}
                if conceded == 0:
                    for pid, row in tgt.items():
                        if mins_t.get(pid, 0) >= MIN_MINS_FULL:
                            cs_t[pid] = CS_POINTS.get(row.get("pos", "MID"), 0)
                # 3) adjusted attack weights for roster (known mins for targets)
                w_adj = {}
                for pid, w in rt["w"].items():
                    if pid in mins_t:
                        w_adj[pid] = w * (mins_t[pid] / 90.0)
                    else:
                        w_adj[pid] = w
                wsum = sum(w_adj.values())
                if scored > 0 and wsum > 0:
                    ids_pool = list(w_adj.keys())
                    probs = [max(v, 0.0) / wsum for v in w_adj.values()]
                    scorers = [int(rng.choice(ids_pool, p=probs)) for _ in range(scored)]
                else:
                    scorers = []
                g_count = Counter(scorers)

                # assists (exclude scorer, over full roster)
                a_count = Counter()
                for s in scorers:
                    others = [pid for pid in w_adj if pid != s and w_adj[pid] > 0]
                    if not others or rng.random() > P_ASSIST:
                        continue
                    ow = [w_adj[pid] for pid in others]
                    os_ = sum(ow)
                    if os_ <= 0:
                        continue
                    a_count[int(rng.choice(others, p=[x / os_ for x in ow]))] += 1

                side_stats.append((tid, oid, mins_t, cs_t, g_count, a_count,
                                   scored, conceded))

            # ---- apply appearance/CS/event points to our targets ----
            for tid, oid, mins_t, cs_t, g_count, a_count, scored, conceded in side_stats:
                tgt = involved.get(tid)
                for pid, row in tgt.items():
                    m = mins_t.get(pid, 0)
                    if m <= 0:
                        continue
                    p = 0.0
                    p += 2 if m >= MIN_MINS_FULL else 1
                    p += cs_t.get(pid, 0)
                    p += _pos_points(row.get("pos", "MID"), g_count.get(pid, 0))
                    p += ASSIST_PTS * a_count.get(pid, 0)
                    pts[pid][it] += p

            # ---- bonus: weighted draw of N_BONUS over both teams ----
            if not side_stats:
                continue
            # Event proxies: real scorers/assisters (we know these for the full
            # roster because allocation draws from the full roster).
            bonus_pool = {}  # pid -> weight
            for tid, oid, mins_t, cs_t, g_count, a_count, scored, conceded in side_stats:
                rt = teams[tid]
                team_cs = conceded == 0
                for pid in rt["rows"]:
                    tend = rt["tend"].get(pid, 0.02)
                    g = g_count.get(pid, 0)
                    a = a_count.get(pid, 0)
                    pos = rt["pos"].get(pid, "MID")
                    event = 2.0 * g + a
                    cs_bonus = 4 if (team_cs and pos in ("GK", "DEF")) else (1 if (team_cs and pos == "MID") else 0)
                    if pid in mins_t:
                        if mins_t.get(pid, 0) <= 0:
                            continue
                        weight = tend * (1.0 + event + cs_bonus)
                    else:
                        # non-involved roster: assume typical involvement
                        weight = tend * (1.0 + event + cs_bonus * 0.35)
                    if weight > 0:
                        bonus_pool[pid] = bonus_pool.get(pid, 0.0) + weight
            if bonus_pool:
                ids_b = list(bonus_pool.keys())
                wb = list(bonus_pool.values())
                pool = [(pid, w) for pid, w in zip(ids_b, wb) if w > 0]
                winners = []
                for _ in range(N_BONUS):
                    if not pool:
                        break
                    tot = sum(w for _, w in pool)
                    if tot <= 0:
                        break
                    r = rng.random() * tot
                    acc = 0.0
                    pick_i = len(pool) - 1
                    for i, (pid, w) in enumerate(pool):
                        acc += w
                        if r <= acc:
                            pick_i = i
                            break
                    winners.append(pool[pick_i][0])
                    pool.pop(pick_i)
                for pid in winners:
                    if pid in pts:
                        pts[pid][it] += 1
    return pts, played


def _row_map(squad_rows):
    return {int(r["id"]): r for r in squad_rows}


def _best_xi_rows(squad_rows):
    """Pick starting XI from squad rows via the deterministic optimizer."""
    from .optimizer import best_xi

    xi = best_xi([{**r} for r in squad_rows])
    if not xi:
        return sorted([r for r in squad_rows if r.get("proj")],
                      key=lambda r: r["proj"], reverse=True)[:11]
    return xi["xi"]


def captain_analysis(gd, df, squad_rows, xi_ids=None, n=600, seed=42):
    """Full captain/vice-captain EV analysis over simulated outcomes.

    Args:
        gd, df: as simulate_gw
        squad_rows: the 15-player squad rows
        xi_ids: optional explicit starting XI ids (default: optimizer XI)

    Returns:
        dict with sorted candidate table (EV incl. best VC pairing) and the
        distribution (p10/p50/p90) of captain points for the recommended pair.
    """
    squad_rows = list(squad_rows)
    by_id = _row_map(squad_rows)

    if xi_ids is not None:
        xi_rows = [by_id[i] for i in xi_ids if i in by_id]
        if len(xi_rows) != 11:
            xi_rows = _best_xi_rows(squad_rows)
    else:
        xi_rows = _best_xi_rows(squad_rows)

    pts, played = simulate_gw(gd, df, squad_rows, n=n, seed=seed)
    ids = [int(r["id"]) for r in xi_rows]

    P = [[pts[i][k] for i in ids] for k in range(n)]
    PL = [[1.0 if played[i][k] else 0.0 for i in ids] for k in range(n)]

    names = {int(r["id"]): (r.get("web_name"), r.get("team_short")) for r in squad_rows}
    proj_of = {int(r["id"]): float(r.get("proj") or 0) for r in squad_rows}

    results = []
    for ci, cid in enumerate(ids):
        ev_no_vc = sum(P[k][ci] * 2.0 * PL[k][ci] for k in range(n)) / n
        p_blank = 1.0 - sum(PL[k][ci] for k in range(n)) / n
        best_vc = None
        best_vc_ev = 0.0
        for vi, vid in enumerate(ids):
            if vid == cid:
                continue
            ev_vc = sum(P[k][vi] * 2.0 * PL[k][vi] * (1.0 - PL[k][ci]) for k in range(n)) / n
            if ev_vc > best_vc_ev:
                best_vc_ev = ev_vc
                best_vc = vid
        results.append({
            "id": cid,
            "web_name": names[cid][0],
            "team_short": names[cid][1],
            "proj": proj_of.get(cid, 0),
            "ev_captain": round(ev_no_vc + best_vc_ev, 2),
            "ev_no_vc": round(ev_no_vc, 2),
            "p_plays": round(1.0 - p_blank, 3),
            "p_blank": round(p_blank, 3),
            "best_vc_id": best_vc,
            "best_vc_name": names[best_vc][0] if best_vc is not None else None,
            "ev_best_vc_effect": round(best_vc_ev, 2),
        })
    results.sort(key=lambda r: r["ev_captain"], reverse=True)
    top = results[0]

    ci = ids.index(top["id"])
    vi = ids.index(top["best_vc_id"]) if top["best_vc_id"] in ids else ci
    cap_series = []
    for k in range(n):
        cpts = P[k][ci] if PL[k][ci] else 0.0
        vpts = P[k][vi] if (not PL[k][ci] and PL[k][vi]) else 0.0
        cap_series.append(2.0 * (cpts + vpts))
    cap_series.sort()
    p10 = cap_series[max(0, int(n * 0.10) - 1)]
    p50 = cap_series[max(0, int(n * 0.50) - 1)]
    p90 = cap_series[min(n - 1, int(n * 0.90))]

    xi_ev = sum(sum(P[k][j] for j in range(len(ids))) for k in range(n)) / n
    return {
        "n": n,
        "xi_ev": round(xi_ev, 2),
        "candidates": results,
        "top": results[0] if results else None,
        "cap_distribution": {"p10": round(p10, 2), "p50": round(p50, 2), "p90": round(p90, 2)},
        "seed": seed,
    }


def load_saved_squad(df):
    """15 full player rows from the saved squad sources (no network).

    Priority: connected FPL team (starters+bench) -> data/squad.json ->
    data/recommended_squad.json.

    Returns (rows, xi_ids, source_label) or (None, None, reason) when no
    complete 15-player squad is available.
    """
    import json

    from .api import DATA_DIR

    df_rows = {int(r["id"]): r for r in df.to_dict("records")}

    def _full(ids):
        out = [df_rows[i] for i in ids if i in df_rows]
        return out if len(out) == 15 else None

    try:
        mgr = json.loads((DATA_DIR / "manager.json").read_text()) if (DATA_DIR / "manager.json").exists() else {}
        starters = mgr.get("starters")
        bench = mgr.get("bench")
        if starters and bench and len(starters) + len(bench) == 15:
            rows = _full(starters + bench)
            if rows:
                return rows, [i for i in starters if i in df_rows], "Tim FPL terhubung"
    except Exception:
        pass

    for fname, label in (("squad.json", "Team Builder (squad.json)"),
                         ("recommended_squad.json", "Rekomendasi CLI (recommended_squad.json)")):
        try:
            path = DATA_DIR / fname
            if path.exists():
                ids = json.loads(path.read_text())
                rows = _full(ids)
                if rows:
                    return rows, None, label
        except Exception:
            continue
    return None, None, "Belum ada skuad 15 pemain tersimpan (sinkronkan via sidebar atau simpan skuad di Team Builder)."


def reference_xi(df, n=11):
    """Greedy synthetic starting XI from the whole pool (club<=3, positions ok).

    Used only when no saved squad exists (e.g. Beranda) as a fair baseline to
    compare captain EV candidates.
    """
    rows = [r for r in df.to_dict("records") if r.get("proj") and r["proj"] > 0]
    rows.sort(key=lambda r: r["proj"], reverse=True)
    picked = []
    club = {}
    pos = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
    max_pos = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
    for r in rows:
        if len(picked) >= n:
            break
        p = r["pos"]
        if pos[p] >= max_pos[p]:
            continue
        t = int(r["team"])
        if club.get(t, 0) >= 3:
            continue
        picked.append(r)
        pos[p] += 1
        club[t] = club.get(t, 0) + 1
    if len(picked) < 11 or pos["DEF"] < 3 or pos["MID"] < 2 or pos["FWD"] < 1:
        # Rare edge (early GW, many blanks): return best available instead.
        return sorted([r for r in rows], key=lambda r: r["proj"], reverse=True)[:n]
    return picked
