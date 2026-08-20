import json
import time

from .api import DATA_DIR, get_element_summary

FILE = DATA_DIR / "paststats.json"
TTL = 24 * 3600


def _stats_from_summary(data):
    hp = data.get("history_past") or []
    if not hp:
        return None
    s = hp[-1]
    pts = int(s.get("total_points") or 0)
    minutes = int(s.get("minutes") or 0)
    starts = int(s.get("starts") or 0)
    games = max(starts, round(minutes / 90))
    return {
        "season": s.get("season_name"),
        "total_points": pts,
        "minutes": minutes,
        "starts": starts,
        "games": games,
        "ppg": round(pts / games, 2) if games else 0.0,
        "goals": int(s.get("goals_scored") or 0),
        "assists": int(s.get("assists") or 0),
        "clean_sheets": int(s.get("clean_sheets") or 0),
        "bonus": int(s.get("bonus") or 0),
    }


def _load_file():
    if FILE.exists():
        try:
            return json.loads(FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_file(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data))


def load(gd, ids=None, force=False):
    data = _load_file()
    fresh = FILE.exists() and time.time() - FILE.stat().st_mtime < TTL
    if fresh and not force:
        return data
    need = [p["id"] for p in gd.players] if ids is None else list(ids)
    for pid in need:
        key = str(pid)
        if key in data:
            continue
        try:
            st = _stats_from_summary(get_element_summary(pid))
            if st:
                data[key] = st
        except Exception:
            pass
    _save_file(data)
    return data


def attach(df, past):
    out = df.copy()

    def g(i, k, default=0):
        return past.get(str(int(i)), {}).get(k, default)

    out["last_points"] = out["id"].map(lambda i: g(i, "total_points"))
    out["last_ppg"] = out["id"].map(lambda i: g(i, "ppg"))
    out["last_goals"] = out["id"].map(lambda i: g(i, "goals"))
    out["last_assists"] = out["id"].map(lambda i: g(i, "assists"))
    out["last_cs"] = out["id"].map(lambda i: g(i, "clean_sheets"))
    out["last_bonus"] = out["id"].map(lambda i: g(i, "bonus"))
    out["last_starts"] = out["id"].map(lambda i: g(i, "starts"))
    out["last_value"] = out.apply(lambda r: round(r["last_points"] / max(r["price"] / 10, 0.5), 2), axis=1)
    return out


def indicator(last_points, last_starts):
    if last_starts >= 15:
        if last_points >= 200:
            return "Bintang musim lalu (≥200 poin)"
        if last_points >= 150:
            return "Sangat baik musim lalu (≥150)"
        if last_points >= 100:
            return "Baik musim lalu (≥100)"
        return "Musim lalu di bawah 100 poin"
    if last_points > 0:
        return "Menit minim musim lalu"
    return "Tanpa riwayat poin musim lalu"
