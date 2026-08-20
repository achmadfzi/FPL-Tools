import pandas as pd

from .utils import FDR_MULT


def project_player(player, fixture, teams_by_id):
    if fixture is None:
        return None
    chance = player.get("chance")
    if chance is None:
        chance = 1.0
    else:
        chance = max(float(chance) / 100.0, 0.0)
    if chance <= 0:
        return None
    if player.get("status") in ("i", "u", "n") and chance < 0.5:
        return None
    own = 0.6 * float(player.get("form") or 0) + 0.4 * float(player.get("ppg") or 0)
    ep_next = float(player.get("ep_next") or 0)
    is_home = fixture["is_home"]
    fdr = fixture["difficulty"]
    home_mult = 1.08 if is_home else 0.93
    fixture_mult = FDR_MULT.get(fdr, 1.0)
    if own > 0:
        final = (0.55 * own * fixture_mult * home_mult + 0.45 * ep_next) * chance
    else:
        final = ep_next * chance
    return {
        "own": round(own, 2),
        "ep_next": round(ep_next, 2),
        "fixture_mult": fixture_mult,
        "home_mult": home_mult,
        "chance": round(chance, 2),
        "is_home": is_home,
        "fdr": fdr,
        "opponent": fixture["opponent"],
        "opponent_short": teams_by_id[fixture["opponent"]]["short_name"],
        "kickoff": fixture.get("kickoff"),
        "final": round(final, 2),
    }


def build_projection_table(gd):
    records = []
    for p in gd.players:
        fixture = gd.fixture_for_team(p["team"])
        meta = project_player(p, fixture, gd.teams_by_id)
        rec = dict(p)
        if meta:
            rec.update(
                {
                    "proj": meta["final"],
                    "own": meta["own"],
                    "ep_next_fpl": meta["ep_next"],
                    "fixture_mult": meta["fixture_mult"],
                    "home_mult": meta["home_mult"],
                    "chance": meta["chance"],
                    "is_home": meta["is_home"],
                    "fdr": meta["fdr"],
                    "opponent_short": meta["opponent_short"],
                    "kickoff": meta["kickoff"],
                }
            )
        else:
            rec.update(
                {
                    "proj": None,
                    "own": 0.0,
                    "ep_next_fpl": 0.0,
                    "fixture_mult": None,
                    "home_mult": None,
                    "chance": 0.0,
                    "is_home": None,
                    "fdr": None,
                    "opponent_short": None,
                    "kickoff": None,
                }
            )
        records.append(rec)
    df = pd.DataFrame(records)
    df["proj"] = pd.to_numeric(df["proj"], errors="coerce")
    return df
