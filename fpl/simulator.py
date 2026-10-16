"""Monte-Carlo Gameweek simulator & captain/vice-captain analysis.

Why: point estimates alone cannot answer "is the top pick also the best
*captain*?" or "should I pick a safer vice-captain?" or "which XI survives
auto-subs best?". This module samples many possible outcomes of a Gameweek
and derives distributions instead of single numbers.

Simulation model (v2):
- match goals:       Poisson(lambda) with lambda from dynamic teamform indices
- goal allocation:   weighted draws among the whole team roster using each
                     player's xG/90 x expected-minutes share
- penalties:         ~10% of goals are penalties, taken by the recognised
                     taker (penalties_order); 78% scored, misses can be saved
                     (opponent GK +5)
- assist allocation: for every open-play goal, a 72% chance of an assist drawn
                     from the scorer's team-mates (self-assist excluded) using
                     xA/90-based weights
- minutes:           drawn around the player's expected minutes (player_history
                     when available, else season minutes-per-start proxy)
- clean sheet:       +4/+4/+1 for GK/DEF/MID that played >= 60 mins
- DefCon:            defenders P(reach 10+ CBIT) / mid+fwds 12+ CBIRT via a
                     Gamma-Poisson model (fpl.defcon), +2 points per hit
- cards:             position-based yellow (-1) / red (-3) probabilities
- GK saves:          Poisson around saves-per-game (3 saves = 1 pt)
- bonus:             top-3 weighted draw over both teams, weights = bonus
                     tendency boosted by goals/assists/CS/DefCon, damped by
                     cards
- captain:           EV = 2x pts if C plays, else 2x pts of the vice-captain
                     if VC plays, else 0 (auto-sub replacement is not doubled)

Auto-sub rules are implemented exactly for lineup evaluation (GK<->bench GK,
outfield subs in bench order, formation must stay valid after every sub).

Deterministic by default (fixed seed) so results are reproducible.
"""

import math
from collections import Counter
from itertools import combinations, permutations

import numpy as np

from .utils import CS_POINTS, DC_POINTS

GOAL_PTS = {"GK": 6, "DEF": 6, "MID": 5, "FWD": 4}
ASSIST_PTS = 3
MIN_MINS_FULL = 60
P_ASSIST = 0.72
N_BONUS = 3

# Penalty model (league averages)
P_GOAL_PEN = 0.10            # share of goals that are penalties
P_PEN_SCORED = 0.78          # conversion rate
P_PEN_SAVED_GIVEN_MISS = 0.35  # of misses, share that are saves (GK +5)

# Card probabilities per match (scaled by minutes)
YELLOW_P = {"GK": 0.03, "DEF": 0.20, "MID": 0.16, "FWD": 0.10}
RED_P = {"GK": 0.006, "DEF": 0.012, "MID": 0.010, "FWD": 0.008}


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


def _per90(row, field, total_field, fallback=0.0):
    """Per-90 rate for `field` (already per-90) or computed from totals."""
    v = row.get(field)
    try:
        if v is not None and not (isinstance(v, float) and math.isnan(v)) and float(v) >= 0:
            return float(v)
    except (TypeError, ValueError):
        pass
    total = float(row.get(total_field) or 0)
    minutes = float(row.get("minutes") or 0)
    if minutes >= 90:
        return total / (minutes / 90.0)
    return fallback


def _xg90(row):
    return _per90(row, "xG_per90", "xG", fallback=0.0)


def _xa90(row):
    return _per90(row, "xA_per90", "xA", fallback=0.0)


def _attack_weight(row):
    """Open-play scoring weight: xG/90 x expected minutes x playing chance."""
    return _xg90(row) * (minutes_proxy(row) / 90.0) * _chance(row)


def _assist_weight(row):
    """Assist weight: xA/90 x expected minutes x playing chance.

    Falls back to the creativity-per-game signal when xA data is missing.
    """
    xa = _xa90(row)
    if xa <= 0:
        crea = float(row.get("creativity_per_game") or 0)
        xa = crea / 90.0  # ~50-60 creativity/game maps to a usable share
    return xa * (minutes_proxy(row) / 90.0) * _chance(row)


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
    """Per-team roster: scoring/assist weights, bonus tendencies, pen taker."""
    teams = {}
    for _, r in df.iterrows():
        tid = int(r["team"])
        pid = int(r["id"])
        entry = teams.setdefault(tid, {
            "rows": {}, "pos": {}, "w": {}, "aw": {}, "tend": {},
            "pen": None, "pen_order": 99, "saves90": {},
        })
        entry["rows"][pid] = r
        entry["pos"][pid] = r.get("pos", "MID")
        tend = float(r.get("bonus_per_game") or 0)
        entry["tend"][pid] = tend if tend > 0 else 0.02
        entry["w"][pid] = _attack_weight(r)
        entry["aw"][pid] = _assist_weight(r)
        try:
            po = r.get("pen_order")
            if po is not None and not (isinstance(po, float) and math.isnan(po)) and int(po) < entry["pen_order"]:
                entry["pen_order"] = int(po)
                entry["pen"] = pid
        except (TypeError, ValueError):
            pass
        saves90 = r.get("saves_per_game")
        try:
            entry["saves90"][pid] = float(saves90) if saves90 and float(saves90) > 0 else 0.0
        except (TypeError, ValueError):
            entry["saves90"][pid] = 0.0
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


def _draw_weighted(rng, pool, weights):
    """Pick from `pool` proportional to `weights` (both same length, w>0)."""
    total = 0.0
    for w in weights:
        total += w
    if total <= 0:
        return None
    r = rng.random() * total
    acc = 0.0
    last = pool[-1]
    for pid, w in zip(pool, weights):
        acc += w
        if r <= acc:
            return pid
        last = pid
    return last


def simulate_gw(gd, df, squad_rows, n=600, seed=42, event_id=None, dc=None):
    """Simulate a Gameweek for a subset of players.

    Args:
        gd: GameData
        df: full projection table (rosters are taken from here)
        squad_rows: list of projection rows whose points we record
        n: number of iterations
        seed: random seed
        event_id: optional target Gameweek (defaults to the next event) —
            used by chip planning for future Gameweeks
        dc: optional DefCon parameters dict (from fpl.defcon)

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
    if event_id is None:
        event_id = gd.next_event["id"]

    if dc is None:
        try:
            from .defcon import load as load_defcon

            dc = load_defcon(gd)
        except Exception:
            dc = {}

    fmap = {tid: gd.fixture_list_for_team_event(tid, event_id) for tid in involved}
    pair_keys = {}
    for tid, fxs in fmap.items():
        for fx in fxs:
            oid = fx["opponent"]
            key = (min(tid, oid), max(tid, oid))
            pair_keys.setdefault(key, []).append((tid, oid, fx["is_home"]))

    pts = {pid: [0.0] * n for pid in all_pids}
    played = {pid: [False] * n for pid in all_pids}

    for it in range(n):
        for _key, entries in pair_keys.items():
            # Determine the actual home/away teams from the entries themselves
            # (the pair key is just min/max ids — never use it as home/away).
            home_entries = [e for e in entries if e[2]]
            away_entries = [e for e in entries if not e[2]]
            if home_entries:
                h_team, a_team = home_entries[0][0], home_entries[0][1]
            else:
                a_team, h_team = away_entries[0][0], away_entries[0][1]
            gh = _goals_lambda(gd, h_team, a_team, True) if home_entries else 0.0
            ga = _goals_lambda(gd, a_team, h_team, False) if away_entries else 0.0
            g_home = int(rng.poisson(lam=gh)) if gh > 0 else 0
            g_away = int(rng.poisson(lam=ga)) if ga > 0 else 0

            sides = []
            if home_entries:
                sides.append((h_team, a_team, True, g_home, g_away))
            if away_entries:
                sides.append((a_team, h_team, False, g_away, g_home))

            # ---- per side: minutes, CS, events ----
            side_stats = []
            pen_save_credits = {}  # team_id -> saves made by its GK this match
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

                # 3) adjusted weights for known minutes
                w_adj = {}
                aw_adj = {}
                for pid in rt["w"]:
                    m_f = mins_t.get(pid, None)
                    if m_f is None:
                        w_adj[pid] = rt["w"][pid]
                        aw_adj[pid] = rt["aw"].get(pid, 0.0)
                    else:
                        scale = (m_f / 90.0) if m_f > 0 else 0.0
                        w_adj[pid] = rt["w"][pid] * scale
                        aw_adj[pid] = rt["aw"].get(pid, 0.0) * scale

                pool = [pid for pid, w in w_adj.items() if w > 0]
                weights = [w_adj[pid] for pid in pool]
                pen_taker = rt.get("pen")

                def _taker_can_play(taker):
                    if taker is None:
                        return False
                    if taker in mins_t:
                        return mins_t[taker] > 0
                    return True  # untracked player: assume he plays (season regular)

                # 4) goals (penalties + open play)
                open_scorers = []
                pen_scorers = []
                for _ in range(scored):
                    if pen_taker is not None and rng.random() < P_GOAL_PEN and _taker_can_play(pen_taker):
                        if rng.random() <= P_PEN_SCORED:
                            pen_scorers.append(pen_taker)
                        elif rng.random() < P_PEN_SAVED_GIVEN_MISS:
                            pen_save_credits[oid] = pen_save_credits.get(oid, 0) + 1
                        continue
                    pick = _draw_weighted(rng, pool, weights)
                    if pick is not None:
                        open_scorers.append(pick)
                g_count = Counter(open_scorers + pen_scorers)

                # 5) assists (open play only; exclude the scorer)
                a_count = Counter()
                for s in open_scorers:
                    if rng.random() > P_ASSIST:
                        continue
                    others = [pid for pid, w in aw_adj.items()
                              if pid != s and w > 0 and (pid not in mins_t or mins_t[pid] > 0)]
                    if not others:
                        continue
                    pick = _draw_weighted(rng, others, [aw_adj[pid] for pid in others])
                    if pick is not None:
                        a_count[pick] += 1

                # 6) cards, DefCon, GK saves
                yc_t, rc_t, dc_t, saves_t = {}, {}, {}, {}
                for pid, row in tgt.items():
                    m = mins_t.get(pid, 0)
                    if m <= 0:
                        continue
                    pos = row.get("pos", "MID")
                    share = m / 90.0
                    if rng.random() < YELLOW_P.get(pos, 0.15) * share:
                        yc_t[pid] = 1
                    if rng.random() < RED_P.get(pos, 0.01) * share:
                        rc_t[pid] = 1
                    if pos in ("DEF", "MID", "FWD"):
                        params = dc.get(str(int(pid))) if dc else None
                        if params:
                            from .defcon import hit_probability

                            p_dc = hit_probability(params.get("pos", pos), params.get("a", 0.0), params.get("b", 1.0), m)
                            if rng.random() < p_dc:
                                dc_t[pid] = 1
                    if pos == "GK" and m >= MIN_MINS_FULL:
                        spg = rt["saves90"].get(pid, 0.0)
                        if spg > 0:
                            saves_t[pid] = int(rng.poisson(lam=spg * share))

                side_stats.append((tid, oid, mins_t, cs_t, g_count, a_count,
                                   scored, conceded, yc_t, rc_t, dc_t, saves_t))

            # ---- penalty saves by the conceding side's GK ----
            # (credits were recorded while the other side was processed)
            if pen_save_credits:
                for tid_credit, count in pen_save_credits.items():
                    tgt_c = involved.get(tid_credit)
                    if not tgt_c:
                        continue
                    # pick the tracked GK with the most minutes this match
                    best_gk, best_m = None, -1
                    for s in side_stats:
                        if s[0] != tid_credit:
                            continue
                        mins_t = s[2]
                        for pid, row in tgt_c.items():
                            if row.get("pos") == "GK" and mins_t.get(pid, 0) > best_m:
                                best_gk, best_m = pid, mins_t.get(pid, 0)
                    if best_gk is not None and best_m > 0:
                        pts[best_gk][it] += 5 * count

            # ---- apply appearance/CS/event points to our targets ----
            for tid, oid, mins_t, cs_t, g_count, a_count, scored, conceded, yc_t, rc_t, dc_t, saves_t in side_stats:
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

                    pos = row.get("pos", "MID")

                    # DefCon points
                    if dc_t.get(pid):
                        p += DC_POINTS

                    # GK save points (3 saves = 1 pt)
                    if pos == "GK":
                        sv = saves_t.get(pid, 0)
                        if sv > 0:
                            p += sv // 3

                    # Cards
                    if yc_t.get(pid):
                        p -= 1
                    if rc_t.get(pid):
                        p -= 3

                    # Goals conceded penalty for GK/DEF: -1 per 2 conceded
                    if pos in ("GK", "DEF") and m >= MIN_MINS_FULL and conceded >= 2:
                        p -= conceded // 2

                    pts[pid][it] += p

            # ---- bonus: weighted draw of N_BONUS over both teams ----
            if not side_stats:
                continue
            bonus_pool = {}  # pid -> weight
            for tid, oid, mins_t, cs_t, g_count, a_count, scored, conceded, yc_t, rc_t, dc_t, saves_t in side_stats:
                rt = teams[tid]
                team_cs = conceded == 0
                for pid in rt["rows"]:
                    tend = rt["tend"].get(pid, 0.02)
                    g = g_count.get(pid, 0)
                    a = a_count.get(pid, 0)
                    pos = rt["pos"].get(pid, "MID")
                    event = 2.0 * g + a
                    cs_bonus = 4 if (team_cs and pos in ("GK", "DEF")) else (1 if (team_cs and pos == "MID") else 0)
                    dc_bonus = 0.6 if dc_t.get(pid) else 0.0
                    card_mod = 0.15 if rc_t.get(pid) else (0.5 if yc_t.get(pid) else 1.0)
                    if pid in mins_t:
                        if mins_t.get(pid, 0) <= 0:
                            continue
                        weight = tend * (1.0 + event + cs_bonus + dc_bonus) * card_mod
                    else:
                        # non-involved roster: assume typical involvement
                        weight = tend * (1.0 + event + cs_bonus * 0.35 + dc_bonus * 0.35)
                    if weight > 0:
                        bonus_pool[pid] = bonus_pool.get(pid, 0.0) + weight
            if bonus_pool:
                ids_b = list(bonus_pool.keys())
                wb = list(bonus_pool.values())
                pool_b = [(pid, w) for pid, w in zip(ids_b, wb) if w > 0]
                winners = []
                for _ in range(N_BONUS):
                    if not pool_b:
                        break
                    tot = sum(w for _, w in pool_b)
                    if tot <= 0:
                        break
                    r = rng.random() * tot
                    acc = 0.0
                    pick_i = len(pool_b) - 1
                    for i, (pid, w) in enumerate(pool_b):
                        acc += w
                        if r <= acc:
                            pick_i = i
                            break
                    winners.append(pool_b[pick_i][0])
                    pool_b.pop(pick_i)
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


def captain_analysis(gd, df, squad_rows, xi_ids=None, n=600, seed=42, event_id=None, dc=None):
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

    pts, played = simulate_gw(gd, df, squad_rows, n=n, seed=seed, event_id=event_id, dc=dc)
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


# ---------------------------------------------------------------------------
# Optimal lineup under exact FPL auto-sub rules
# ---------------------------------------------------------------------------


def _lineup_candidates(squad_rows):
    """All valid starting XI combos (formations x players, club rule applied).

    Returns list of dicts: {"xi": [cols], "bench": [cols], "formation": (d,m,f)}
    where cols are indices into squad_rows order.
    """
    from .optimizer import FORMATIONS

    idx_by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    clubs = []
    pos_of = []
    for i, r in enumerate(squad_rows):
        p = r.get("pos", "MID")
        idx_by_pos.setdefault(p, []).append(i)
        clubs.append(int(r.get("team", 0)))
        pos_of.append(p)

    out = []
    for nd, nm, nf in FORMATIONS:
        if len(idx_by_pos["DEF"]) < nd or len(idx_by_pos["MID"]) < nm or len(idx_by_pos["FWD"]) < nf:
            continue
        for gk in combinations(idx_by_pos["GK"], 1):
            for defs in combinations(idx_by_pos["DEF"], nd):
                for mids in combinations(idx_by_pos["MID"], nm):
                    for fwds in combinations(idx_by_pos["FWD"], nf):
                        xi = list(gk) + list(defs) + list(mids) + list(fwds)
                        picked = set(xi)
                        club_count = Counter(clubs[i] for i in xi)
                        if max(club_count.values(), default=0) > 3:
                            continue
                        bench = [i for i in range(len(squad_rows)) if i not in picked]
                        out.append({"xi": xi, "bench": bench, "formation": (nd, nm, nf)})
    return out


def autosub_points(P, PL, xi_cols, bench_cols, pos_of):
    """Points per iteration for a lineup under exact FPL auto-sub rules.

    Vectorised over iterations. P: (n, L) points, PL: (n, L) bool played.
    Returns np.ndarray (n,) with the XI total points after substitutions.
    """
    n = P.shape[0]
    starters = list(xi_cols)
    Pts = P[:, starters].copy()
    Played = PL[:, starters].copy()
    n_start = len(starters)
    replaced = np.zeros((n, n_start), dtype=bool)
    starter_pos = [pos_of[c] for c in starters]
    cnt = {p: np.full(n, starter_pos.count(p), dtype=int) for p in ("DEF", "MID", "FWD")}
    lo = {"DEF": 3, "MID": 2, "FWD": 1}
    hi = {"DEF": 5, "MID": 5, "FWD": 3}

    for b in bench_cols:
        pos_b = pos_of[b]
        bench_plays = PL[:, b]
        if pos_b == "GK":
            for j, c in enumerate(starters):
                if pos_of[c] != "GK":
                    continue
                take = (~Played[:, j]) & (~replaced[:, j]) & bench_plays
                if take.any():
                    Pts[take, j] = P[take, b]
                    replaced[take, j] = True
            continue

        done = np.zeros(n, dtype=bool)
        for j, c in enumerate(starters):
            q = pos_of[c]
            if q == "GK":
                continue
            ok_def = cnt["DEF"] - (1 if q == "DEF" else 0) + (1 if pos_b == "DEF" else 0)
            ok_mid = cnt["MID"] - (1 if q == "MID" else 0) + (1 if pos_b == "MID" else 0)
            ok_fwd = cnt["FWD"] - (1 if q == "FWD" else 0) + (1 if pos_b == "FWD" else 0)
            valid = (
                (ok_def >= lo["DEF"]) & (ok_def <= hi["DEF"])
                & (ok_mid >= lo["MID"]) & (ok_mid <= hi["MID"])
                & (ok_fwd >= lo["FWD"]) & (ok_fwd <= hi["FWD"])
            )
            take = (~Played[:, j]) & (~replaced[:, j]) & bench_plays & valid & (~done)
            if take.any():
                Pts[take, j] = P[take, b]
                replaced[take, j] = True
                if pos_b in cnt:
                    cnt[pos_b][take] += 1
                if q in cnt:
                    cnt[q][take] -= 1
                done |= take

    return Pts.sum(axis=1)


def simulate_squad_matrices(gd, df, squad_rows, n=600, seed=42, event_id=None, dc=None):
    """Simulate a squad and return numpy matrices ready for lineup/chip math.

    Returns dict: {ids, pos_of, P (n x 15), PL (n x 15), pts, played, n, seed}
    """
    squad_rows = list(squad_rows)
    pts, played = simulate_gw(gd, df, squad_rows, n=n, seed=seed, event_id=event_id, dc=dc)
    ids = [int(r["id"]) for r in squad_rows]
    P = np.zeros((n, len(ids)))
    PL = np.zeros((n, len(ids)), dtype=bool)
    for j, pid in enumerate(ids):
        P[:, j] = pts[pid]
        PL[:, j] = played[pid]
    return {
        "ids": ids,
        "pos_of": [r.get("pos", "MID") for r in squad_rows],
        "P": P,
        "PL": PL,
        "pts": pts,
        "played": played,
        "n": n,
        "seed": seed,
    }


def optimal_lineup(gd, df, squad_rows, n=600, seed=42, event_id=None, dc=None, refine=15, sim=None):
    """Pick the XI + bench order maximising EV under FPL auto-sub rules.

    Uses one simulation of the whole squad (pass `sim` from
    simulate_squad_matrices to reuse an existing one), then evaluates every
    valid formation/XI combination exactly (including auto-subs) and refines
    the bench order of the best candidates.

    Returns dict with xi_ids, bench_ids (ordered 1-3 + GK), ev, formation,
    ev_naive (sum of projections), and captain/vice EV info.
    """
    squad_rows = list(squad_rows)
    if sim is None:
        sim = simulate_squad_matrices(gd, df, squad_rows, n=n, seed=seed, event_id=event_id, dc=dc)
    P, PL = sim["P"], sim["PL"]
    n_iter = P.shape[0]
    pos_of = sim["pos_of"]
    proj_of = [float(r.get("proj") or 0) for r in squad_rows]

    candidates = _lineup_candidates(squad_rows)

    # Initial bench order: outfield by projection desc, GK last.
    def _default_bench(bench):
        out = [i for i in bench if pos_of[i] != "GK"]
        gk = [i for i in bench if pos_of[i] == "GK"]
        out.sort(key=lambda i: proj_of[i], reverse=True)
        return out + gk

    scored = []
    for cand in candidates:
        bench = _default_bench(cand["bench"])
        ev = float(autosub_points(P, PL, cand["xi"], bench, pos_of).mean())
        scored.append((ev, cand, bench))
    scored.sort(key=lambda x: x[0], reverse=True)

    best = None
    for ev0, cand, bench in scored[: max(1, refine)]:
        outfield = [i for i in bench if pos_of[i] != "GK"]
        gk = [i for i in bench if pos_of[i] == "GK"]
        best_order = bench
        best_ev = ev0
        for perm in permutations(outfield):
            order = list(perm) + gk
            ev = float(autosub_points(P, PL, cand["xi"], order, pos_of).mean())
            if ev > best_ev:
                best_ev = ev
                best_order = order
        if best is None or best_ev > best["ev"]:
            best = {
                "ev": best_ev,
                "xi": cand["xi"],
                "bench": best_order,
                "formation": cand["formation"],
                "cand": cand,
            }

    xi_cols = best["xi"]
    bench_cols = best["bench"]

    # Captain/vice EV inside this XI (double + VC insurance when C blanks).
    cap_results = []
    for ci in xi_cols:
        ev_c = float((P[:, ci] * PL[:, ci]).mean() * 2.0)
        p_blank = float((~PL[:, ci]).mean())
        best_vc, best_vc_ev = None, 0.0
        for vi in xi_cols:
            if vi == ci:
                continue
            ev_vc = float((P[:, vi] * PL[:, vi] * (~PL[:, ci])).mean() * 2.0)
            if ev_vc > best_vc_ev:
                best_vc, best_vc_ev = vi, ev_vc
        cap_results.append({"col": ci, "ev_captain": ev_c + best_vc_ev,
                            "ev_no_vc": ev_c, "p_blank": p_blank,
                            "vc_col": best_vc, "ev_vc": best_vc_ev})
    cap_results.sort(key=lambda r: r["ev_captain"], reverse=True)
    cap_best = cap_results[0]

    # Distribution of aligned captain EV for the recommendation
    ci, vi = cap_best["col"], cap_best["vc_col"]
    if vi is not None:
        series = 2.0 * (P[:, ci] * PL[:, ci] + P[:, vi] * PL[:, vi] * (~PL[:, ci]))
    else:
        series = 2.0 * (P[:, ci] * PL[:, ci])
    series = np.sort(series)
    dist = {
        "p10": round(float(series[max(0, int(n_iter * 0.10) - 1)]), 2),
        "p50": round(float(series[max(0, int(n_iter * 0.50) - 1)]), 2),
        "p90": round(float(series[min(n_iter - 1, int(n_iter * 0.90))]), 2),
    }

    id_of = sim["ids"]

    def _info(col):
        r = squad_rows[col]
        return {
            "id": id_of[col],
            "web_name": r.get("web_name"),
            "team_short": r.get("team_short"),
            "pos": pos_of[col],
            "proj": proj_of[col],
            "ev": round(float((P[:, col] * PL[:, col]).mean()), 2),
            "p_play": round(float(PL[:, col].mean()), 3),
        }

    def _order_info(cols):
        out = []
        for i, col in enumerate(cols, 1):
            info = _info(col)
            info["bench_slot"] = i if pos_of[col] != "GK" else "GK"
            out.append(info)
        return out

    xi_info = sorted([_info(c) for c in xi_cols], key=lambda r: r["ev"], reverse=True)

    cap_info = _info(ci)
    cap_info["ev_captain"] = round(cap_best["ev_captain"], 2)
    cap_info["ev_no_vc"] = round(cap_best["ev_no_vc"], 2)
    cap_info["vc_name"] = squad_rows[vi].get("web_name") if vi is not None else None
    cap_info["p_blank"] = round(cap_best["p_blank"], 3)
    vice_info = _info(vi) if vi is not None else None

    return {
        "n": n_iter,
        "seed": seed,
        "ev": round(best["ev"], 2),
        "ev_naive": round(sum(proj_of[c] for c in xi_cols), 2),
        "formation": best["formation"],
        "xi_ids": [id_of[c] for c in xi_cols],
        "xi": xi_info,
        "bench_ids": [id_of[c] for c in bench_cols],
        "bench": _order_info(bench_cols),
        "captain": cap_info,
        "vice": vice_info,
        "captain_distribution": dist,
        "candidates_top": [
            {"ev": round(ev0, 2), "formation": cand["formation"]}
            for ev0, cand, _ in scored[:5]
        ],
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
