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
            out[f["team_h"]] = {
                "opponent": f["team_a"],
                "difficulty": f["team_h_difficulty"],
                "is_home": True,
                "kickoff": f.get("kickoff_time"),
            }
            out[f["team_a"]] = {
                "opponent": f["team_h"],
                "difficulty": f["team_a_difficulty"],
                "is_home": False,
                "kickoff": f.get("kickoff_time"),
            }
        return out

    def _build_players(self):
        players = []
        for p in self.bootstrap["elements"]:
            team = self.teams_by_id[p["team"]]
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
                    "xGI": float(p.get("expected_goal_involvements") or 0),
                    "xG": float(p.get("expected_goals") or 0),
                    "xA": float(p.get("expected_assists") or 0),
                    "threat": float(p.get("threat") or 0),
                    "creativity": float(p.get("creativity") or 0),
                    "influence": float(p.get("influence") or 0),
                    "minutes": p.get("minutes") or 0,
                    "starts": p.get("starts") or 0,
                    "photo_code": p.get("photo") or "",
                    "price_change": p.get("cost_change_start") or 0,
                }
            )
        return players

    def fixture_for_team(self, team_id):
        return self.fixtures_by_team.get(team_id)

    def fixture_for_team_event(self, team_id, event_id):
        for f in self.fixtures:
            if f.get("event") != event_id:
                continue
            if f["team_h"] == team_id:
                return {"opponent": f["team_a"], "difficulty": f["team_h_difficulty"], "is_home": True, "kickoff": f.get("kickoff_time")}
            if f["team_a"] == team_id:
                return {"opponent": f["team_h"], "difficulty": f["team_a_difficulty"], "is_home": False, "kickoff": f.get("kickoff_time")}
        return None

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


def get_game_data(force=False):
    bootstrap = get_bootstrap(force=force)
    fixtures = get_fixtures(force=force)
    return GameData(bootstrap, fixtures)
