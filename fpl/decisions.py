"""Decision-level accuracy for the FPL dashboard.

Projection MAE answers "how far off is the model per player?".  Users care
about a different question: "did the captain pick return points, and did the
recommended transfer beat holding?".  This module records the actual
recommendations shown by the dashboard and evaluates them once the Gameweek
has finished.

Captain history already exists inside ``accuracy.json`` (top projected player
per GW).  New recommendations are stored in ``recommendations.json`` so the
real EV-based captain, transfer advice, chip choice and lineup can be
evaluated going forward.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .api import DATA_DIR

ACCURACY_FILE = DATA_DIR / "accuracy.json"
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"


def _load(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _deadline_ts(deadline_iso: str | None) -> float | None:
    if not deadline_iso:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(deadline_iso).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _gw_sort_key(key: str) -> int:
    try:
        return int(key.split("_")[1])
    except (IndexError, ValueError):
        return 0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pct(part: float, total: float) -> float:
    return round(100.0 * part / total, 1) if total else 0.0


def _result(points: int) -> str:
    if points >= 8:
        return "haul"
    if points >= 4:
        return "return"
    return "blank"


# ---------------------------------------------------------------------------
# Write path: keep the latest pre-deadline recommendation for each GW
# ---------------------------------------------------------------------------


def save_recommendation(
    gw_id: int,
    deadline: str | None,
    captain: dict | None = None,
    transfer: dict | None = None,
    chips: dict | None = None,
    lineup: dict | None = None,
    source: str = "",
) -> bool:
    """Store the latest recommendation shown before the deadline.

    Returns True when the file was updated.  After the deadline the stored
    entry is frozen, so opening the dashboard late cannot rewrite history.
    """
    key = f"gw_{int(gw_id)}"
    data = _load(RECOMMENDATIONS_FILE)
    now = time.time()
    deadline_ts = _deadline_ts(deadline)
    if deadline_ts is not None and now > deadline_ts:
        # Never record advice that can no longer be acted on.
        return False

    cap = None
    if captain:
        cap = {
            "id": int(captain.get("id")),
            "name": captain.get("name") or captain.get("web_name"),
            "team": captain.get("team") or captain.get("team_short"),
            "pos": captain.get("pos"),
            "proj": captain.get("proj"),
            "ev": captain.get("ev_captain", captain.get("ev")),
            "p_play": captain.get("p_play"),
            "p_blank": captain.get("p_blank"),
            "p_haul": captain.get("p_haul"),
        }

    tr = None
    if transfer and transfer.get("transfers"):
        rows = []
        for t in transfer["transfers"]:
            if not t.get("out_id") or not t.get("in_id"):
                continue
            rows.append({
                "out_id": int(t["out_id"]),
                "out_name": t.get("out_name"),
                "in_id": int(t["in_id"]),
                "in_name": t.get("in_name"),
            })
        if rows:
            tr = {
                "transfers": rows,
                "hits": int(transfer.get("hits") or 0),
                "headline": transfer.get("headline"),
                "gain": transfer.get("gain"),
            }

    ch = None
    if chips:
        gains = chips.get("gains") if isinstance(chips.get("gains"), dict) else {}
        ch = {
            "headline": chips.get("headline"),
            "metric": chips.get("metric"),
            "available": chips.get("available"),
            "gains": {str(k): v for k, v in gains.items()},
        }

    ln = None
    if lineup:
        cap_info = lineup.get("captain") or {}
        vice_info = lineup.get("vice") or {}
        try:
            ln = {
                "xi_ids": [int(x) for x in (lineup.get("xi_ids") or [])],
                "bench_ids": [int(x) for x in (lineup.get("bench_ids") or [])],
                "formation": lineup.get("formation"),
                "ev": lineup.get("ev"),
                "captain_id": int(cap_info["id"]) if cap_info.get("id") is not None else None,
                "vice_id": int(vice_info["id"]) if vice_info.get("id") is not None else None,
            }
        except (TypeError, ValueError):
            ln = None

    data[key] = {
        "saved_at": now,
        "deadline": deadline,
        "source": source,
        "captain": cap,
        "transfer": tr,
        "chips": ch,
        "lineup": ln,
    }
    _save(RECOMMENDATIONS_FILE, data)
    return True


# ---------------------------------------------------------------------------
# Read path: evaluate captain and transfer decisions
# ---------------------------------------------------------------------------


def _captain_rows(accuracy: dict, recommendations: dict) -> list[dict]:
    rows: list[dict] = []
    for key in sorted(accuracy, key=_gw_sort_key):
        if not key.startswith("gw_"):
            continue
        entry = accuracy[key] or {}
        actuals = entry.get("actuals") or {}
        projections = entry.get("projections") or {}
        if not actuals or not projections:
            continue

        pairs = []
        for pid, info in projections.items():
            if pid not in actuals:
                continue
            proj = info.get("proj_served", info.get("proj"))
            try:
                proj = float(proj)
            except (TypeError, ValueError):
                continue
            pairs.append({
                "id": int(pid),
                "name": info.get("web_name") or pid,
                "team": info.get("team_short") or "",
                "pos": info.get("pos") or "",
                "proj": proj,
                "actual": int(actuals[pid]),
            })
        if not pairs:
            continue

        tracked = (recommendations.get(key) or {}).get("captain") or {}
        picked = None
        source = "proxy"
        if tracked.get("id") is not None:
            tid = int(tracked["id"])
            picked = next((p for p in pairs if p["id"] == tid), None)
            if picked is not None:
                source = "rekomendasi"
        if picked is None:
            picked = max(pairs, key=lambda p: p["proj"])

        ranked = sorted(pairs, key=lambda p: p["proj"], reverse=True)
        top10 = ranked[:10]
        field_avg = _mean([p["actual"] for p in pairs])
        oracle = max(pairs, key=lambda p: p["actual"])
        beaten = sum(1 for p in pairs if p["actual"] < picked["actual"])

        rows.append({
            "gw": _gw_sort_key(key),
            "source": source,
            "captain_id": picked["id"],
            "captain": picked["name"],
            "team": picked["team"],
            "pos": picked["pos"],
            "proj": round(picked["proj"], 2),
            "actual": picked["actual"],
            "result": _result(picked["actual"]),
            "percentile": round(100.0 * beaten / len(pairs), 1),
            "field_avg": round(field_avg, 2),
            "regret": oracle["actual"] - picked["actual"],
            "oracle": oracle["name"],
            "oracle_actual": oracle["actual"],
            "top10_n": len(top10),
            "top10_returns": sum(1 for p in top10 if p["actual"] >= 4),
            "top10_hauls": sum(1 for p in top10 if p["actual"] >= 8),
            "top10_avg": round(_mean([p["actual"] for p in top10]), 2),
        })
    return rows


def _transfer_rows(accuracy: dict, recommendations: dict) -> list[dict]:
    rows: list[dict] = []
    for key in sorted(recommendations, key=_gw_sort_key):
        if not key.startswith("gw_"):
            continue
        rec = recommendations[key] or {}
        tr = rec.get("transfer")
        if not tr or not tr.get("transfers"):
            continue
        gw = _gw_sort_key(key)
        entry = accuracy.get(key) or {}
        actuals = entry.get("actuals") or {}
        hits = int(tr.get("hits") or 0)
        base = {
            "gw": gw,
            "headline": tr.get("headline") or "",
            "hits": hits,
            "transfers": tr.get("transfers") or [],
        }
        if not actuals:
            rows.append({**base, "status": "pending"})
            continue

        out_pts = 0
        in_pts = 0
        missing = False
        for t in tr["transfers"]:
            o = actuals.get(str(t["out_id"]))
            i = actuals.get(str(t["in_id"]))
            if o is None or i is None:
                missing = True
                break
            out_pts += int(o)
            in_pts += int(i)
        if missing:
            rows.append({**base, "status": "pending"})
            continue

        net = in_pts - out_pts - 4 * hits
        rows.append({
            **base,
            "status": "done",
            "out_points": out_pts,
            "in_points": in_pts,
            "hit_cost": 4 * hits,
            "net": net,
            "result": "win" if net > 0 else "loss" if net < 0 else "tie",
        })
    return rows


def decision_summary() -> dict:
    """Return captain/transfer hit-rate snapshots for the performance page."""
    accuracy = _load(ACCURACY_FILE)
    recommendations = _load(RECOMMENDATIONS_FILE)

    captain_rows = _captain_rows(accuracy, recommendations)
    transfer_rows = _transfer_rows(accuracy, recommendations)

    n_gws = len(captain_rows)
    returns = sum(1 for r in captain_rows if r["actual"] >= 4)
    hauls = sum(1 for r in captain_rows if r["actual"] >= 8)
    blanks = sum(1 for r in captain_rows if r["actual"] < 4)
    avg_points = round(_mean([r["actual"] for r in captain_rows]), 2)
    avg_field = round(_mean([r["field_avg"] for r in captain_rows]), 2)
    top10_n = sum(r["top10_n"] for r in captain_rows)
    top10_returns = sum(r["top10_returns"] for r in captain_rows)
    top10_hauls = sum(r["top10_hauls"] for r in captain_rows)
    top10_points = round(_mean([r["top10_avg"] for r in captain_rows]), 2)

    done = [r for r in transfer_rows if r.get("status") == "done"]
    wins = sum(1 for r in done if r["result"] == "win")
    losses = sum(1 for r in done if r["result"] == "loss")
    ties = sum(1 for r in done if r["result"] == "tie")
    avg_net = round(_mean([r["net"] for r in done]), 2)
    pending = sum(1 for r in transfer_rows if r.get("status") == "pending")

    return {
        "captain": {
            "n_gws": n_gws,
            "return_rate": _pct(returns, n_gws),
            "haul_rate": _pct(hauls, n_gws),
            "blank_rate": _pct(blanks, n_gws),
            "avg_points": avg_points,
            "avg_field_points": avg_field,
            "lift": round(avg_points / avg_field, 2) if avg_field else None,
            "avg_regret": round(_mean([r["regret"] for r in captain_rows]), 2) if captain_rows else 0.0,
            "top10": {
                "n_players": top10_n,
                "return_rate": _pct(top10_returns, top10_n),
                "haul_rate": _pct(top10_hauls, top10_n),
                "avg_points": top10_points,
                "lift": round(top10_points / avg_field, 2) if avg_field else None,
            },
            "by_gw": captain_rows,
            "tracked_gws": sum(1 for r in captain_rows if r["source"] == "rekomendasi"),
        },
        "transfer": {
            "n": len(done),
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "win_rate": _pct(wins, len(done)),
            "avg_net": avg_net,
            "pending": pending,
            "by_gw": transfer_rows,
        },
        "notes": [
            "Kapten historis memakai proxy proyeksi tertinggi; rekomendasi EV dicatat otomatis mulai GW berjalan.",
            "Transfer dievaluasi pada GW pertama setelah rekomendasi: (poin pemain masuk - poin keluar - hit).",
            "Sampel kecil: hasil per GW bisa berubah cepat. Gunakan sebagai indikator, bukan jaminan.",
        ],
    }
