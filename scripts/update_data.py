#!/usr/bin/env python3
"""Scheduled data refresh for the FPL dashboard.

Run this from cron/GitHub Actions instead of relying on a browser tab:

    .venv/bin/python scripts/update_data.py --all

Typical schedule:
    * every 30 minutes before a deadline (or T-24h / T-6h / T-1h)
    * once after the Gameweek finishes, with ``--backfill``
"""

from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fpl import accuracy, defcon, player_history  # noqa: E402
from fpl.api import clear_cache, get_game_data  # noqa: E402
from fpl.model import build_projection_table  # noqa: E402
from fpl.snapshots import save_projection_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh FPL dashboard data")
    parser.add_argument("--all", action="store_true", help="run every refresh step")
    parser.add_argument("--force", action="store_true", help="ignore API cache")
    parser.add_argument("--backfill", action="store_true", help="refresh per-player history")
    parser.add_argument("--history-limit", type=int, default=None,
                        help="cap players fetched during backfill")
    parser.add_argument("--min-minutes", type=int, default=180,
                        help="only backfill players with at least this many minutes")
    parser.add_argument("--snapshot", action="store_true", help="save a projection snapshot")
    parser.add_argument("--accuracy", action="store_true", help="fetch actuals / compute metrics")
    parser.add_argument("--calibrate", action="store_true", help="fit calibration after update")
    parser.add_argument("--quiet", action="store_true", help="less output")
    args = parser.parse_args()

    if args.all:
        args.backfill = args.snapshot = args.accuracy = True

    started = time.time()
    if args.force:
        clear_cache()
    gd = get_game_data(force=args.force)
    gw = int(gd.next_event["id"])
    if not args.quiet:
        print(f"GW {gw} · {len(gd.players)} players · {len(gd.fixtures)} fixtures")

    if args.backfill:
        res = player_history.backfill_if_stale(
            gd,
            min_minutes=args.min_minutes,
            limit=args.history_limit,
            progress=None if args.quiet else (
                lambda i, n, name: print(f"  history {i}/{n} {name}", end="\r")
            ),
        )
        if not args.quiet:
            print()
            print(f"history: fetched={res['fetched']} skipped={res['skipped']} failed={res['failed']}")
        defcon.build(gd, force=True)

    df = build_projection_table(gd)

    if args.snapshot:
        path = save_projection_snapshot(
            gw, df, deadline=gd.next_event.get("deadline_time"),
            force=True, source="scheduled",
        )
        if not args.quiet:
            print(f"snapshot: {path}")

    # Keep accuracy.json pointed at the latest pre-deadline state.
    try:
        accuracy.save_projections(gw, df, force=False)
    except Exception as exc:
        if not args.quiet:
            print(f"save_projections failed: {exc}")

    if args.accuracy:
        updated = accuracy.auto_update_history()
        if not args.quiet:
            print(f"accuracy: updated {updated} GW(s)")

    if args.calibrate:
        from fpl import calibration

        result = calibration.fit()
        if not args.quiet:
            print(f"calibration: enabled={result.get('enabled')} method={result.get('method')}")

    if not args.quiet:
        print(f"done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
