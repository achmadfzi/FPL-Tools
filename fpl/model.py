import pandas as pd

from .utils import (
    BONUS_BASELINE,
    CREATIVITY_NORM_FACTOR,
    CS_POINTS,
    FDR_MULT,
    ICT_BASELINE,
    THREAT_NORM_FACTOR,
    XGI_PER90_BASELINE,
)


def _minutes_consistency_factor(player):
    """Calculate a multiplier based on how consistently a player plays full games.

    Players who always play 90 minutes get 1.0.
    Players who are regularly substituted or rotated get a penalty.
    New players (no starts) get a neutral 0.85.
    """
    starts = player.get("starts") or 0
    minutes = player.get("minutes") or 0

    if starts == 0 or minutes == 0:
        # No match data yet — neutral factor
        return 0.85

    mins_per_start = minutes / max(starts, 1)

    if mins_per_start >= 85:
        return 1.0  # Nailed-on starter, plays full games
    elif mins_per_start >= 75:
        return 0.95  # Usually plays most of the game
    elif mins_per_start >= 60:
        return 0.88  # Often substituted or comes on as sub
    elif mins_per_start >= 45:
        return 0.78  # Significant rotation risk
    else:
        return 0.65  # Heavy rotation / impact sub


def project_player(player, fixtures, gd):
    """Project a player's points for the next GW.

    Args:
        player: dict with player stats
        fixtures: list of fixture dicts (supports DGW with multiple fixtures)
        gd: GameData instance (for cs_probability, teams_by_id)

    Enhanced formula v2:
        base = 0.40 × form + 0.20 × ppg + 0.25 × xGI_signal + 0.15 × ict_signal
        cs_bonus = cs_prob × cs_points_for_pos × 0.15
        threat_bonus = threat_norm × 0.08
        bonus_tendency = bonus_per_game_norm × 0.08
        creativity_bonus = creativity_norm × 0.06
        base_adj = base + cs_bonus + threat_bonus + bonus_tendency + creativity_bonus
        per_fixture = base_adj × FDR_mult × home_mult
        final = (0.65 × sum(per_fixture) + 0.25 × ep_next + 0.10 × ep_next_safety) × chance × minutes_factor
    """
    if not fixtures:
        return None

    # --- Playing chance ---
    chance = player.get("chance")
    if chance is None:
        chance = 1.0
    else:
        chance = max(float(chance) / 100.0, 0.0)
    if chance <= 0:
        return None
    if player.get("status") in ("i", "u", "n") and chance < 0.5:
        return None

    # --- Base quality signal (enhanced with ICT) ---
    form = float(player.get("form") or 0)
    ppg = float(player.get("ppg") or 0)
    xgi_per90 = float(player.get("xGI_per90") or 0)

    # Normalize xGI per 90 to a similar scale as form (0-10)
    xgi_signal = min(xgi_per90 / XGI_PER90_BASELINE, 1.0) * max(form, ppg, 2.0) if XGI_PER90_BASELINE > 0 else 0.0

    # ICT Index signal — combines influence, creativity, threat into one score
    ict_per_game = float(player.get("ict_per_game") or 0)
    ict_signal = min(ict_per_game / ICT_BASELINE, 1.5) * max(form, ppg, 2.0) if ICT_BASELINE > 0 else 0.0

    base = 0.40 * form + 0.20 * ppg + 0.25 * xgi_signal + 0.15 * ict_signal

    ep_next = float(player.get("ep_next") or 0)
    pos = player.get("pos", "MID")

    # --- Threat bonus (attacking signal, normalized) ---
    threat = float(player.get("threat") or 0)
    minutes = player.get("minutes") or 0
    games_played = max(minutes / 90.0, 1.0) if minutes > 0 else 1.0
    threat_per_game = threat / games_played
    threat_norm = min(threat_per_game / THREAT_NORM_FACTOR, 1.0)
    threat_bonus = threat_norm * 0.08

    # --- Bonus points tendency ---
    bonus_per_game = float(player.get("bonus_per_game") or 0)
    bonus_norm = min(bonus_per_game / BONUS_BASELINE, 1.5)
    bonus_tendency = bonus_norm * 0.08

    # --- Creativity bonus (assists/chance creation signal) ---
    creativity_per_game = float(player.get("creativity_per_game") or 0)
    creativity_norm = min(creativity_per_game / CREATIVITY_NORM_FACTOR, 1.0)
    creativity_bonus = creativity_norm * 0.06

    # --- Minutes consistency multiplier ---
    minutes_factor = _minutes_consistency_factor(player)

    # --- Per-fixture projection (handles DGW) ---
    fixture_projs = []
    fixture_metas = []

    for fixture in fixtures:
        is_home = fixture["is_home"]
        fdr = fixture["difficulty"]
        opponent = fixture["opponent"]
        home_mult = 1.08 if is_home else 0.93
        fixture_mult = FDR_MULT.get(fdr, 1.0)

        # Clean sheet probability bonus
        cs_prob = gd.cs_probability(player["team"], opponent, is_home, fdr=fdr)
        cs_pts = CS_POINTS.get(pos, 0)
        cs_bonus = cs_prob * cs_pts * 0.15

        base_adj = base + cs_bonus + threat_bonus + bonus_tendency + creativity_bonus

        fx_proj = base_adj * fixture_mult * home_mult
        fixture_projs.append(fx_proj)
        fixture_metas.append({
            "is_home": is_home,
            "fdr": fdr,
            "opponent": opponent,
            "opponent_short": gd.teams_by_id[opponent]["short_name"],
            "kickoff": fixture.get("kickoff"),
            "fixture_mult": fixture_mult,
            "home_mult": home_mult,
            "cs_prob": round(cs_prob, 3),
        })

    # Sum across fixtures (DGW = 2 fixtures summed)
    own_total = sum(fixture_projs)
    n_fixtures = len(fixtures)

    # Blend own model with FPL's ep_next
    # v2: More weight on own model (65%) vs FPL ep_next (25% + 10% safety)
    if base > 0:
        # For DGW, ep_next from FPL should already account for double, but we scale defensively
        ep_weight = ep_next * (1.0 if n_fixtures == 1 else 1.5)
        final = (0.65 * own_total + 0.25 * ep_weight + 0.10 * ep_next) * chance * minutes_factor
    else:
        # No form/ppg data (e.g. GW1) — lean heavily on ep_next
        final = ep_next * chance * minutes_factor * (1.0 if n_fixtures == 1 else 1.8)

    # Use first fixture for primary display metadata
    primary = fixture_metas[0]

    return {
        "own": round(base, 2),
        "own_total": round(own_total, 2),
        "ep_next": round(ep_next, 2),
        "fixture_mult": primary["fixture_mult"],
        "home_mult": primary["home_mult"],
        "cs_prob": primary["cs_prob"],
        "threat_norm": round(threat_norm, 3),
        "xgi_signal": round(xgi_signal, 2),
        "ict_signal": round(ict_signal, 2),
        "bonus_norm": round(bonus_norm, 3),
        "creativity_norm": round(creativity_norm, 3),
        "minutes_factor": round(minutes_factor, 2),
        "chance": round(chance, 2),
        "is_home": primary["is_home"],
        "fdr": primary["fdr"],
        "opponent": primary["opponent"],
        "opponent_short": primary["opponent_short"],
        "kickoff": primary["kickoff"],
        "n_fixtures": n_fixtures,
        "final": round(final, 2),
        "fixture_details": fixture_metas,
    }


def build_projection_table(gd):
    records = []
    for p in gd.players:
        fixtures = gd.fixture_list_for_team(p["team"])
        meta = project_player(p, fixtures, gd)
        rec = dict(p)
        if meta:
            rec.update(
                {
                    "proj": meta["final"],
                    "own": meta["own"],
                    "own_total": meta["own_total"],
                    "ep_next_fpl": meta["ep_next"],
                    "fixture_mult": meta["fixture_mult"],
                    "home_mult": meta["home_mult"],
                    "cs_prob": meta["cs_prob"],
                    "threat_norm": meta["threat_norm"],
                    "xgi_signal": meta["xgi_signal"],
                    "ict_signal": meta["ict_signal"],
                    "bonus_norm": meta["bonus_norm"],
                    "creativity_norm": meta["creativity_norm"],
                    "minutes_factor": meta["minutes_factor"],
                    "chance": meta["chance"],
                    "is_home": meta["is_home"],
                    "fdr": meta["fdr"],
                    "opponent_short": meta["opponent_short"],
                    "kickoff": meta["kickoff"],
                    "n_fixtures": meta["n_fixtures"],
                }
            )
        else:
            rec.update(
                {
                    "proj": None,
                    "own": 0.0,
                    "own_total": 0.0,
                    "ep_next_fpl": 0.0,
                    "fixture_mult": None,
                    "home_mult": None,
                    "cs_prob": 0.0,
                    "threat_norm": 0.0,
                    "xgi_signal": 0.0,
                    "ict_signal": 0.0,
                    "bonus_norm": 0.0,
                    "creativity_norm": 0.0,
                    "minutes_factor": 0.0,
                    "chance": 0.0,
                    "is_home": None,
                    "fdr": None,
                    "opponent_short": None,
                    "kickoff": None,
                    "n_fixtures": 0,
                }
            )
        records.append(rec)
    df = pd.DataFrame(records)
    df["proj"] = pd.to_numeric(df["proj"], errors="coerce")
    return df
