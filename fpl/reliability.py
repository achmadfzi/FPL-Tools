import json
import time

from .api import DATA_DIR, get_element_summary

FILE = DATA_DIR / "reliability.json"
TTL = 24 * 3600


def _minutes(pid):
    try:
        d = get_element_summary(pid)
        hp = d.get("history_past") or []
        if hp:
            s = hp[-1]
            return {
                "minutes": int(s.get("minutes") or 0),
                "starts": int(s.get("starts") or 0),
                "season": s.get("season_name"),
                "has_history": True,
            }
    except Exception:
        pass
    return {"minutes": 0, "starts": 0, "season": None, "has_history": False}


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


def factor(minutes, has_history, selected_by=0.0):
    if has_history:
        if minutes >= 2000:
            minutes_factor = 1.0
        elif minutes >= 1500:
            minutes_factor = 0.95
        elif minutes >= 1000:
            minutes_factor = 0.88
        elif minutes >= 500:
            minutes_factor = 0.72
        else:
            minutes_factor = 0.5
    else:
        minutes_factor = 0.6
    community = round(0.6 + 0.4 * min(max(float(selected_by or 0), 0.0) / 20.0, 1.0), 2)
    return round(max(minutes_factor, community), 2)


def label(minutes, has_history, selected_by=0.0):
    community = 0.6 + 0.4 * min(max(float(selected_by or 0), 0.0) / 20.0, 1.0)
    if community >= 0.75 and community > factor(minutes, has_history, 0.0) + 1e-9:
        if community >= 0.95:
            return "Dipercaya komunitas"
        return "Dilirik komunitas"
    if has_history:
        if minutes >= 2000:
            return "Mapan (starter musim lalu)"
        if minutes >= 1000:
            return "Cukup mapan"
        if minutes > 0:
            return "Risiko menit bermain"
        return "Tanpa menit musim lalu"
    return "Pemain baru / belum terbukti"


def load(gd, ids=None, force=False):
    data = _load_file()
    fresh = FILE.exists() and time.time() - FILE.stat().st_mtime < TTL
    if not fresh or force:
        need = [p["id"] for p in gd.players] if ids is None else list(ids)
        for pid in need:
            key = str(pid)
            if key not in data:
                data[key] = _minutes(pid)
        _save_file(data)
    return data


def adjust(df, rel):
    out = df.copy()

    def _min(i):
        return int(rel.get(str(int(i)), {}).get("minutes", 0))

    def _has(i):
        return bool(rel.get(str(int(i)), {}).get("has_history", False))

    out["rel_minutes"] = out["id"].map(_min)
    out["rel_has_history"] = out["id"].map(_has)
    out["rel_factor"] = out.apply(
        lambda r: factor(r["rel_minutes"], r["rel_has_history"], r["selected_by"]), axis=1
    )
    out["rel_label"] = out.apply(
        lambda r: label(r["rel_minutes"], r["rel_has_history"], r["selected_by"]), axis=1
    )
    out["proj_raw"] = out["proj"]
    out["proj"] = out["proj"] * out["rel_factor"]
    return out
