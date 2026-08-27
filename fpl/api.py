import json
import time
from pathlib import Path

import requests

from .utils import POSITION_NAMES

BASE_URL = "https://fantasy.premierleague.com/api"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "cache.json"
DEFAULT_TTL = 60 * 60
LONG_TTL = 6 * 60 * 60

_HEADERS = {"User-Agent": "Mozilla/5.0 (FPL Dashboard)"}


def _load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache))


def clear_cache():
    cache = _load_cache()
    cache.clear()
    _save_cache(cache)


def _fetch_json(url, ttl=DEFAULT_TTL, force=False):
    cache = _load_cache()
    entry = cache.get(url)
    if not force and entry and time.time() - entry["ts"] < ttl:
        return entry["data"]
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    cache[url] = {"ts": time.time(), "data": resp.json()}
    _save_cache(cache)
    return cache[url]["data"]


def get_bootstrap(force=False):
    return _fetch_json(f"{BASE_URL}/bootstrap-static/", force=force)


def get_fixtures(force=False):
    return _fetch_json(f"{BASE_URL}/fixtures/", force=force)


def get_element_summary(player_id, force=False):
    return _fetch_json(f"{BASE_URL}/element-summary/{player_id}/", ttl=LONG_TTL, force=force)


def get_entry(team_id, force=False):
    """Fetch manager and team profile by FPL Team ID."""
    return _fetch_json(f"{BASE_URL}/entry/{team_id}/", ttl=1800, force=force)


def get_entry_picks(team_id, event_id, force=False):
    """Fetch squad picks for a team at a specific gameweek."""
    return _fetch_json(f"{BASE_URL}/entry/{team_id}/event/{event_id}/picks/", ttl=1800, force=force)


def get_entry_history(team_id, force=False):
    """Fetch team score history, chips played, and classic league info."""
    return _fetch_json(f"{BASE_URL}/entry/{team_id}/history/", ttl=1800, force=force)


def get_entry_transfers(team_id, force=False):
    """Fetch transfer history for a team."""
    return _fetch_json(f"{BASE_URL}/entry/{team_id}/transfers/", ttl=1800, force=force)


class GameData:
    def __init__(self, bootstrap, fixtures):
        self.bootstrap = bootstrap
        self.fixtures = fixtures
        self.teams_by_id = {t["id"]: t for t in bootstrap["teams"]}
        self.positions = {
            et["id"]: POSITION_NAMES.get(et["id"], et["singular_name_short"])
            for et in bootstrap["element_types"]
        }
        self.events = bootstrap["events"]
        self.next_event = self._next_event()
        self.fixtures_by_team = self._fixtures_by_team()
        self.team_strength = self._team_strength()
        self.players = self._build_players()

    def _next_event(self):
        for e in self.events:
            if e.get("is_next"):
                return e
        for e in self.events:
            if not e.get("finished"):
                return e
        return self.events[0]

    def _fixtures_by_team(self):
        event_id = self.next_event["id"]
        out = {}
        for f in self.fixtures:
            if f.get("event") != event_id:
                continue
            out.setdefault(f["team_h"], []).append({
                "opponent": f["team_a"],
                "difficulty": f["team_h_difficulty"],
                "is_home": True,
                "kickoff": f.get("kickoff_time"),
            })
            out.setdefault(f["team_a"], []).append({
                "opponent": f["team_h"],
                "difficulty": f["team_a_difficulty"],
                "is_home": False,
                "kickoff": f.get("kickoff_time"),
            })
        return out

    def _team_strength(self):
        """Extract team strength ratings for CS probability estimation."""
        out = {}
        for t in self.bootstrap["teams"]:
            # FPL provides strength_attack/defence_home/away on 1-5 scale (roughly)
            out[t["id"]] = {
                "attack_home": t.get("strength_attack_home", 1200),
                "attack_away": t.get("strength_attack_away", 1200),
                "defence_home": t.get("strength_defence_home", 1200),
                "defence_away": t.get("strength_defence_away", 1200),
                "overall": t.get("strength_overall_home", 1200),
                "short_name": t["short_name"],
            }
        return out

    def cs_probability(self, team_id, opponent_id, is_home, fdr=None):
        """Estimate clean sheet probability based on team strength ratings.

        Uses ratio of defending team's defence strength vs opponent's attack strength.
        Falls back to FDR-based estimation when strength data is unavailable (e.g. GW1).
        Returns a value between 0.05 and 0.55.
        """
        ts = self.team_strength
        if team_id not in ts or opponent_id not in ts:
            return self._cs_from_fdr(fdr, is_home)

        if is_home:
            defence = ts[team_id]["defence_home"]
            attack = ts[opponent_id]["attack_away"]
        else:
            defence = ts[team_id]["defence_away"]
            attack = ts[opponent_id]["attack_home"]

        # If strength values are 0 (season start), fall back to FDR
        if defence <= 0 or attack <= 0:
            return self._cs_from_fdr(fdr, is_home)

        # Ratio > 1 means defence stronger than opponent attack → higher CS chance
        ratio = defence / attack

        # Map ratio to probability: ratio=1.0 → ~0.30, ratio=1.2 → ~0.42, ratio=0.8 → ~0.18
        cs_prob = 0.30 * ratio
        return max(0.05, min(0.55, cs_prob))

    @staticmethod
    def _cs_from_fdr(fdr, is_home):
        """Estimate CS probability from FDR when strength data unavailable."""
        fdr_cs = {1: 0.40, 2: 0.35, 3: 0.28, 4: 0.20, 5: 0.15}
        base = fdr_cs.get(fdr, 0.28)
        # Home teams keep clean sheets ~5% more often
        return max(0.05, min(0.55, base + (0.05 if is_home else 0.0)))

    def _build_players(self):
        players = []
        for p in self.bootstrap["elements"]:
            team = self.teams_by_id[p["team"]]
            minutes = p.get("minutes") or 0
            xgi = float(p.get("expected_goal_involvements") or 0)
            # Compute xGI per 90 minutes (avoid division by zero)
            xgi_per90 = round(xgi / (minutes / 90.0), 2) if minutes >= 90 else 0.0
            players.append(
                {
                    "id": p["id"],
                    "web_name": p["web_name"],
                    "known_name": p.get("known_name") or p["web_name"],
                    "team": p["team"],
                    "team_short": team["short_name"],
                    "team_name": team["name"],
                    "pos": self.positions[p["element_type"]],
                    "price": p["now_cost"],
                    "form": float(p.get("form") or 0),
                    "ppg": float(p.get("points_per_game") or 0),
                    "total_points": p.get("total_points") or 0,
                    "selected_by": float(p.get("selected_by_percent") or 0),
                    "status": p.get("status") or "a",
                    "news": p.get("news") or "",
                    "ep_next": float(p.get("ep_next") or 0),
                    "chance": p.get("chance_of_playing_next_round"),
                    "xGI": xgi,
                    "xGI_per90": xgi_per90,
                    "xG": float(p.get("expected_goals") or 0),
                    "xA": float(p.get("expected_assists") or 0),
                    "threat": float(p.get("threat") or 0),
                    "creativity": float(p.get("creativity") or 0),
                    "influence": float(p.get("influence") or 0),
                    "minutes": minutes,
                    "starts": p.get("starts") or 0,
                    "photo_code": p.get("photo") or "",
                    "price_change": p.get("cost_change_start") or 0,
                }
            )
        return players

    def fixture_for_team(self, team_id):
        """Return first fixture for team in next GW (backward compat)."""
        fxs = self.fixtures_by_team.get(team_id, [])
        return fxs[0] if fxs else None

    def fixture_list_for_team(self, team_id):
        """Return ALL fixtures for team in next GW (supports DGW)."""
        return self.fixtures_by_team.get(team_id, [])

    def fixture_for_team_event(self, team_id, event_id):
        for f in self.fixtures:
            if f.get("event") != event_id:
                continue
            if f["team_h"] == team_id:
                return {"opponent": f["team_a"], "difficulty": f["team_h_difficulty"], "is_home": True, "kickoff": f.get("kickoff_time")}
            if f["team_a"] == team_id:
                return {"opponent": f["team_h"], "difficulty": f["team_a_difficulty"], "is_home": False, "kickoff": f.get("kickoff_time")}
        return None

    def fixture_list_for_team_event(self, team_id, event_id):
        """Return ALL fixtures for team in a given event (supports DGW)."""
        out = []
        for f in self.fixtures:
            if f.get("event") != event_id:
                continue
            if f["team_h"] == team_id:
                out.append({"opponent": f["team_a"], "difficulty": f["team_h_difficulty"], "is_home": True, "kickoff": f.get("kickoff_time")})
            if f["team_a"] == team_id:
                out.append({"opponent": f["team_h"], "difficulty": f["team_a_difficulty"], "is_home": False, "kickoff": f.get("kickoff_time")})
        return out

    def fixtures_by_event_map(self):
        out = {}
        for f in self.fixtures:
            out.setdefault(f.get("event"), []).append(f)
        return out

    def team_fixture_counts(self, event_id):
        counts = {}
        for f in self.fixtures:
            if f.get("event") == event_id:
                counts[f["team_h"]] = counts.get(f["team_h"], 0) + 1
                counts[f["team_a"]] = counts.get(f["team_a"], 0) + 1
        return counts

    def fixture_ticker(self, n_gws=6):
        """Return FDR for next N gameweeks per team. Used for fixture swing analysis.

        Returns: {team_id: [{"gw": N, "opponent": id, "fdr": int, "is_home": bool}, ...]}
        """
        cur = self.next_event["id"]
        ticker = {t: [] for t in self.teams_by_id}
        for gw in range(cur, cur + n_gws):
            for f in self.fixtures:
                if f.get("event") != gw:
                    continue
                ticker[f["team_h"]].append({
                    "gw": gw,
                    "opponent": f["team_a"],
                    "opponent_short": self.teams_by_id[f["team_a"]]["short_name"],
                    "fdr": f["team_h_difficulty"],
                    "is_home": True,
                })
                ticker[f["team_a"]].append({
                    "gw": gw,
                    "opponent": f["team_h"],
                    "opponent_short": self.teams_by_id[f["team_h"]]["short_name"],
                    "fdr": f["team_a_difficulty"],
                    "is_home": False,
                })
        return ticker


def get_game_data(force=False):
    bootstrap = get_bootstrap(force=force)
    fixtures = get_fixtures(force=force)
    return GameData(bootstrap, fixtures)

