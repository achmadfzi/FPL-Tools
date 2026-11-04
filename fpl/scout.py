"""Official FPL Scout Selection: fetch, parse, cache, and compare.

The Scout Selection is published on premierleague.com as an article. The
Premier League content API exposes the same article body as HTML, which lets
us extract the 11 picks without scraping the rendered page.

Data is used as a *second opinion*: the model's projections are not changed.
"""

import html as _html
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests

from .api import DATA_DIR

SCOUT_API = "https://api.premierleague.com/content/premierleague/TEXT/en"
SCOUT_TAG = '("franchise:fpl-scout-picks")'
CACHE_FILE = DATA_DIR / "scout_selection.json"
CACHE_TTL = 6 * 60 * 60
HEADERS = {
    "User-Agent": "Mozilla/5.0 (FPL Dashboard)",
    "Origin": "https://www.premierleague.com",
    "Referer": "https://www.premierleague.com/",
}

# Common article spellings that fuzzy matching alone can miss.
TEAM_ALIASES = {
    "arsenal": "ARS",
    "aston villa": "AVL",
    "afc bournemouth": "BOU",
    "bournemouth": "BOU",
    "brentford": "BRE",
    "brighton": "BHA",
    "brighton and hove albion": "BHA",
    "chelsea": "CHE",
    "coventry": "COV",
    "coventry city": "COV",
    "crystal palace": "CRY",
    "everton": "EVE",
    "fulham": "FUL",
    "hull": "HUL",
    "hull city": "HUL",
    "ipswich": "IPS",
    "ipswich town": "IPS",
    "leeds": "LEE",
    "leeds united": "LEE",
    "liverpool": "LIV",
    "man city": "MCI",
    "manchester city": "MCI",
    "man utd": "MUN",
    "manchester united": "MUN",
    "newcastle": "NEW",
    "newcastle united": "NEW",
    "nott m forest": "NFO",
    "nottm forest": "NFO",
    "nottingham forest": "NFO",
    "sunderland": "SUN",
    "spurs": "TOT",
    "tottenham": "TOT",
    "tottenham hotspur": "TOT",
    "west ham": "WHU",
    "west ham united": "WHU",
    "wolves": "WOL",
    "wolverhampton wanderers": "WOL",
}


def _norm(text):
    """Lowercase, accent-free, punctuation-free name for matching."""
    value = _html.unescape(str(text or ""))
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _clean_html_text(body):
    value = re.sub(r"<script.*?</script>", " ", body or "", flags=re.S | re.I)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", _html.unescape(value)).strip()


def _parse_date(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _season_start(gd):
    """Approximate season start from the first FPL deadline."""
    try:
        deadlines = [
            _parse_date(e.get("deadline_time"))
            for e in gd.events
            if e.get("deadline_time")
        ]
        deadlines = [d for d in deadlines if d is not None]
        if deadlines:
            return min(deadlines) - timedelta(days=45)
    except Exception:
        pass
    return datetime.now(timezone.utc) - timedelta(days=330)


def _gw_from_title(title):
    match = re.search(r"Gameweek\s+(\d+)", title or "", re.I)
    return int(match.group(1)) if match else None


def build_player_index(gd):
    """Compact index with all useful name variants for matching."""
    index = []
    for p in gd.bootstrap.get("elements", []):
        team = gd.teams_by_id.get(p.get("team"), {})
        aliases = {
            p.get("web_name"),
            p.get("known_name"),
            f"{p.get('first_name', '')} {p.get('second_name', '')}".strip(),
            p.get("second_name"),
        }
        index.append({
            "id": int(p["id"]),
            "name": p.get("web_name") or p.get("second_name") or "",
            "pos": gd.positions.get(p.get("element_type"), "MID"),
            "team": team.get("short_name", ""),
            "team_name": team.get("name", ""),
            "price": int(p.get("now_cost") or 0),
            "aliases": [a for a in aliases if a],
            "norm_aliases": [_norm(a) for a in aliases if a],
        })
    return index


def build_team_map(gd):
    out = {}
    for t in gd.bootstrap.get("teams", []):
        short = t.get("short_name", "")
        for name in (t.get("name"), short):
            if name:
                out[_norm(name)] = short
    for name, short in TEAM_ALIASES.items():
        out[_norm(name)] = short
    return out


def _resolve_team(raw_team, team_map):
    key = _norm(raw_team)
    if not key:
        return None
    if key in team_map:
        return team_map[key]
    best_short, best_score = None, 0.0
    for name, short in team_map.items():
        score = SequenceMatcher(None, key, name).ratio()
        if score > best_score:
            best_short, best_score = short, score
    return best_short if best_score >= 0.72 else None


def _resolve_player(raw_name, raw_team, raw_price, player_index, team_map):
    """Map an article name to an FPL element; return (player, score) or (None, score)."""
    key = _norm(raw_name)
    team = _resolve_team(raw_team, team_map)
    candidates = [p for p in player_index if not team or p["team"] == team]
    if not candidates:
        candidates = player_index

    scored = []
    for p in candidates:
        best = 0.0
        for alias in p["norm_aliases"]:
            if not alias:
                continue
            if key == alias:
                best = 1.0
                break
            best = max(best, SequenceMatcher(None, key, alias).ratio())
        score = best * 100.0
        if team and p["team"] == team:
            score += 15.0
        if raw_price and abs((p["price"] / 10.0) - float(raw_price)) < 0.051:
            score += 10.0
        scored.append((score, p))

    if not scored:
        return None, 0.0
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_player = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if top_score < 70 or (top_score - second_score) < 3 and top_score < 105:
        return None, top_score
    return top_player, top_score


def _nearest_player(text, players, patterns):
    """Find the player whose name is closest to a captain/vice phrase."""
    lower = _norm(text)
    positions = []
    for pattern in patterns:
        positions.extend(m.start() for m in re.finditer(pattern, _norm(text), re.I))
    if not positions:
        return None
    best_id, best_distance = None, 10_000
    fallback_id, fallback_distance = None, 10_000
    for p in players:
        aliases = p.get("norm_aliases") or [
            _norm(p.get("raw_name")),
            _norm(p.get("name")),
        ]
        for alias in aliases:
            if not alias:
                continue
            # Match whole-ish names to avoid short surnames matching inside words.
            for m in re.finditer(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lower):
                # The player is nearly always named BEFORE "captain" or
                # "vice-captain" ("Palmer given the vice-captaincy").
                before = [pos for pos in positions if m.start() <= pos]
                if before:
                    distance = min(pos - m.start() for pos in before)
                    if distance < best_distance:
                        best_id, best_distance = p["id"], distance
                else:
                    distance = min(abs(m.start() - pos) for pos in positions)
                    if distance < fallback_distance:
                        fallback_id, fallback_distance = p["id"], distance
    if best_id is not None and best_distance <= 180:
        return best_id
    return fallback_id if fallback_distance <= 60 else None


def _captain_ids(text, players):
    captain = _nearest_player(text, players, [
        r"named as captain",
        r"captain's armband",
        r"handed the captain",
        r"given the captain",
        r"wears the armband",
        r"captain for",
    ])
    vice = _nearest_player(text, players, [
        r"vice[- ]captain(?:cy)?",
        r"vice[- ]captain",
    ])
    if captain is None:
        # Generic fallback, excluding "vice-captain" occurrences.
        norm_text = _norm(text)
        generic_positions = [
            m.start()
            for m in re.finditer(r"captain", norm_text)
            if "vice" not in norm_text[max(0, m.start() - 12):m.start()]
        ]
        if generic_positions:
            lower = norm_text
            best_id, best_distance = None, 10_000
            for p in players:
                aliases = p.get("norm_aliases") or [
                    _norm(p.get("raw_name")),
                    _norm(p.get("name")),
                ]
                for alias in aliases:
                    if not alias:
                        continue
                    for m in re.finditer(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lower):
                        before = [pos for pos in generic_positions if m.start() <= pos]
                        if not before:
                            continue
                        distance = min(pos - m.start() for pos in before)
                        if distance < best_distance:
                            best_id, best_distance = p["id"], distance
            if best_distance <= 150:
                captain = best_id
    return captain, vice


def parse_article_body(body, title, date, url, player_index, team_map):
    """Parse one Scout Selection article body into a structured selection."""
    headings = []
    for match in re.finditer(r"<h5[^>]*>(.*?)</h5>", body or "", re.S | re.I):
        text = _clean_html_text(match.group(1))
        heading = re.match(
            r"(.+?)\s*\(([^)]+)\)\s*£\s*([0-9]+(?:\.[0-9]+)?)m",
            text,
            re.I,
        )
        if heading:
            headings.append({
                "raw_name": heading.group(1).strip(),
                "raw_team": heading.group(2).strip(),
                "raw_price": float(heading.group(3)),
            })

    players = []
    unresolved = []
    for item in headings:
        player, score = _resolve_player(
            item["raw_name"],
            item["raw_team"],
            item["raw_price"],
            player_index,
            team_map,
        )
        if player is None:
            unresolved.append({**item, "score": round(score, 1)})
            continue
        players.append({
            "element_id": player["id"],
            "id": player["id"],
            "raw_name": item["raw_name"],
            "raw_team": item["raw_team"],
            "raw_price": item["raw_price"],
            "name": player["name"],
            "pos": player["pos"],
            "team": player["team"],
            "price": player["price"],
            "match_score": round(score, 1),
        })

    text = _clean_html_text(body)
    captain_id, vice_id = _captain_ids(text, players)
    counts = Counter(p["pos"] for p in players)
    formation = None
    if len(players) == 11 and counts.get("GK") == 1:
        formation = f"{counts.get('DEF', 0)}-{counts.get('MID', 0)}-{counts.get('FWD', 0)}"

    return {
        "id": None,
        "gw": _gw_from_title(title),
        "title": title,
        "date": date,
        "url": url,
        "type": "xi" if len(headings) == 11 else "squad",
        "formation": formation,
        "captain_id": captain_id,
        "vice_id": vice_id,
        "players": players,
        "unresolved": unresolved,
    }


def _fetch_remote(gd):
    params = {
        "contentTypes": "TEXT",
        "offset": 0,
        "limit": 50,
        "onlyRestrictedContent": "false",
        "detail": "DETAILED",
        "tagExpression": SCOUT_TAG,
    }
    resp = requests.get(SCOUT_API, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    player_index = build_player_index(gd)
    team_map = build_team_map(gd)
    season_start = _season_start(gd)
    articles = []
    for content in payload.get("content", []):
        title = content.get("title") or ""
        if not title.startswith("Scout Selection"):
            continue
        published = _parse_date(content.get("date"))
        if published is None or published < season_start:
            continue
        article_id = int(content.get("id") or 0)
        slug = content.get("titleUrlSegment") or ""
        url = f"https://www.premierleague.com/en/news/{article_id}/{slug}" if article_id else ""
        selection = parse_article_body(
            content.get("body") or "",
            title,
            content.get("date"),
            url,
            player_index,
            team_map,
        )
        selection["id"] = article_id
        articles.append(selection)
    return articles


def _load_cache():
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(articles):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({
        "fetched_at": time.time(),
        "articles": articles,
    }, indent=2))


def load_articles(gd, force=False):
    """Current-season Scout Selection articles (cached 6 hours)."""
    cached = _load_cache()
    if not force and cached and time.time() - cached.get("fetched_at", 0) < CACHE_TTL:
        return cached.get("articles", [])
    try:
        articles = _fetch_remote(gd)
        _save_cache(articles)
        return articles
    except Exception:
        # Stale cache is better than an empty panel.
        return (cached or {}).get("articles", [])


def latest_selection(gd, current_gw, force=False):
    """Current GW selection, or the latest previous GW when not released.

    Returns a dict with ``selection``, ``requested_gw`` and ``is_current``.
    """
    articles = [
        a for a in load_articles(gd, force=force)
        if a.get("type") == "xi" and a.get("gw") is not None
    ]
    if not articles:
        return None
    exact = [a for a in articles if int(a["gw"]) == int(current_gw)]
    if exact:
        return {
            "selection": sorted(exact, key=lambda a: a.get("date") or "", reverse=True)[0],
            "requested_gw": int(current_gw),
            "is_current": True,
        }
    previous = [a for a in articles if int(a["gw"]) <= int(current_gw)]
    if not previous:
        return None
    return {
        "selection": sorted(previous, key=lambda a: (a.get("gw") or 0, a.get("date") or ""), reverse=True)[0],
        "requested_gw": int(current_gw),
        "is_current": False,
    }


def get_selection_by_url(url, gd):
    """Manual fallback: parse an official article URL."""
    match = re.search(r"/news/(\d+)", url or "")
    if not match:
        raise ValueError("URL artikel tidak valid")
    article_id = int(match.group(1))
    resp = requests.get(
        f"{SCOUT_API}/{article_id}",
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()
    selection = parse_article_body(
        content.get("body") or "",
        content.get("title") or "",
        content.get("date"),
        url,
        build_player_index(gd),
        build_team_map(gd),
    )
    selection["id"] = article_id
    return selection


def compare_selection(selection, xi_ids, players_by_id, captain_id=None, squad_ids=None):
    """Compare a Scout XI with the user's XI/squad."""
    scout_ids = [int(p["element_id"]) for p in selection.get("players", [])]
    user_ids = [int(i) for i in xi_ids or []]
    scout_set, user_set = set(scout_ids), set(user_ids)
    overlap = [i for i in scout_ids if i in user_set]
    only_scout = [i for i in scout_ids if i not in user_set]
    only_user = [i for i in user_ids if i not in scout_set]

    def _proj(ids):
        return round(sum(float(players_by_id[i].get("proj") or 0) for i in ids if i in players_by_id), 2)

    scout_captain = selection.get("captain_id")
    scout_captain_name = players_by_id.get(scout_captain, {}).get("web_name") if scout_captain else None
    user_captain = captain_id
    user_captain_name = players_by_id.get(user_captain, {}).get("web_name") if user_captain else None
    squad_set = set(int(i) for i in (squad_ids or []))

    return {
        "overlap_ids": overlap,
        "only_scout_ids": only_scout,
        "only_user_ids": only_user,
        "overlap_count": len(overlap),
        "agreement_pct": round(100.0 * len(overlap) / max(len(scout_ids), 1), 1),
        "scout_total": _proj(scout_ids),
        "user_total": _proj(user_ids),
        "captain_match": bool(scout_captain and user_captain and int(scout_captain) == int(user_captain)),
        "scout_captain": scout_captain_name,
        "user_captain": user_captain_name,
        "not_owned_ids": [i for i in scout_ids if i not in squad_set],
        "scout_ids": scout_ids,
    }
