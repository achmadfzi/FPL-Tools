"""Timestamped projection snapshots.

The dashboard is often opened several times before a deadline.  A single
``accuracy.json`` projection entry is not enough: team news can change in the
final hours, and we need the *last* pre-deadline state for honest evaluation
while still keeping earlier states for research.

This module stores one JSON file per snapshot under
``data/snapshots/gw_<id>/<unix-ts>.json``.  Snapshots are intentionally
self-contained (all model features + served projection) so a future model can
be re-fitted without relying on today's bootstrap payload.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from .api import DATA_DIR

SNAPSHOT_DIR = DATA_DIR / "snapshots"
MAX_PER_GW = 8
MIN_INTERVAL_SECONDS = 300


def _gw_dir(gw_id: int) -> Path:
    return SNAPSHOT_DIR / f"gw_{int(gw_id)}"


def _safe(value):
    """Convert pandas/numpy/date values into JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    try:
        # numpy scalar
        if hasattr(value, "item"):
            value = value.item()
            if isinstance(value, float) and math.isnan(value):
                return None
            return value
    except Exception:
        pass
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        if hasattr(value, "isoformat"):
            return value.isoformat()
    except Exception:
        pass
    return str(value)


def _deadline_ts(deadline_iso: str | None) -> float | None:
    if not deadline_iso:
        return None
    try:
        return datetime.fromisoformat(str(deadline_iso).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _snapshot_files(gw_id: int) -> list[Path]:
    d = _gw_dir(gw_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime)


def _prune(gw_id: int) -> None:
    files = _snapshot_files(gw_id)
    for path in files[:-MAX_PER_GW]:
        try:
            path.unlink()
        except OSError:
            pass


def save_projection_snapshot(
    gw_id: int,
    df,
    deadline: str | None = None,
    force: bool = False,
    min_interval: int = MIN_INTERVAL_SECONDS,
    source: str = "dashboard",
) -> Path | None:
    """Persist the current projection table for one Gameweek.

    Returns the path written, or ``None`` when throttled / empty.  The writer
    is intentionally cheap: the heavy lifting is already in ``df``.
    """
    if df is None or len(df) == 0:
        return None

    gw_id = int(gw_id)
    files = _snapshot_files(gw_id)
    if files and not force:
        age = time.time() - files[-1].stat().st_mtime
        if age < max(0, int(min_interval)):
            return files[-1]

    rows = []
    for _, row in df.iterrows():
        proj = row.get("proj")
        try:
            if proj is None or (isinstance(proj, float) and math.isnan(proj)):
                continue
        except Exception:
            continue
        payload = {}
        for key, value in row.to_dict().items():
            payload[str(key)] = _safe(value)
        # Keep the served and raw values explicitly, even when calibration
        # columns are absent (normal case).
        payload["proj_raw"] = _safe(row.get("proj_pre_cal", proj))
        payload["proj_served"] = _safe(proj)
        rows.append(payload)

    if not rows:
        return None

    payload = {
        "gw": gw_id,
        "saved_at": time.time(),
        "saved_at_iso": datetime.now(timezone.utc).isoformat(),
        "deadline": deadline,
        "source": source,
        "n": len(rows),
        "projections": rows,
    }
    d = _gw_dir(gw_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{int(time.time() * 1000)}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False))
    tmp.replace(path)
    _prune(gw_id)
    return path


def load_snapshot(path: Path | str) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def list_snapshots(gw_id: int, load_full: bool = False) -> list[dict]:
    """Metadata for every stored snapshot of a Gameweek, oldest first.

    By default only file metadata is read (fast); pass ``load_full=True`` when
    the caller needs the payload fields as well.
    """
    out = []
    for path in _snapshot_files(gw_id):
        stat = path.stat()
        item = {
            "path": path,
            "saved_at": stat.st_mtime,
            "saved_at_iso": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "deadline": None,
            "n": None,
            "source": None,
        }
        if load_full:
            payload = load_snapshot(path)
            if payload is None:
                continue
            item.update({
                "saved_at": payload.get("saved_at", item["saved_at"]),
                "saved_at_iso": payload.get("saved_at_iso", item["saved_at_iso"]),
                "deadline": payload.get("deadline"),
                "n": payload.get("n", len(payload.get("projections", []))),
                "source": payload.get("source"),
            })
        out.append(item)
    return out


def latest_snapshot(gw_id: int, before: float | None = None) -> dict | None:
    """Latest snapshot, optionally only those with ``saved_at < before``."""
    best = None
    for path in _snapshot_files(gw_id):
        payload = load_snapshot(path)
        if payload is None:
            continue
        saved = float(payload.get("saved_at") or path.stat().st_mtime)
        if before is not None and saved >= before:
            continue
        if best is None or saved > float(best.get("saved_at") or 0):
            best = payload
            best["_path"] = str(path)
    return best


def pre_deadline_snapshot(gw_id: int, deadline: str | None) -> dict | None:
    """Last snapshot taken before the Gameweek deadline.

    If the deadline is unknown, returns the latest snapshot.  This is the
    snapshot that should be used for accuracy evaluation.
    """
    ts = _deadline_ts(deadline)
    if ts is None:
        return latest_snapshot(gw_id)
    return latest_snapshot(gw_id, before=ts)


def snapshot_rows(snapshot: dict | None) -> list[dict]:
    if not snapshot:
        return []
    rows = snapshot.get("projections") or []
    return rows if isinstance(rows, list) else []


def snapshot_projections(snapshot: dict | None) -> dict:
    """Return ``{player_id: row}`` for convenient metric computations."""
    out = {}
    for row in snapshot_rows(snapshot):
        try:
            out[str(int(row.get("id")))] = row
        except (TypeError, ValueError):
            continue
    return out


def freshness(gw_id: int) -> dict:
    """Human friendly age of the latest snapshot for a Gameweek."""
    files = _snapshot_files(gw_id)
    if not files:
        return {"available": False, "age_seconds": None, "latest": None}
    latest = files[-1]
    age = max(0.0, time.time() - latest.stat().st_mtime)
    return {
        "available": True,
        "age_seconds": round(age, 1),
        "age_minutes": round(age / 60.0, 1),
        "latest": latest,
        "path": str(latest),
    }
