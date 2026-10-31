"""Tests for the phase 0-4 improvements.

Runnable with plain Python or pytest:

    .venv/bin/python tests/test_improvements.py
"""

import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fpl import accuracy, calibration, planner, snapshots  # noqa: E402
from fpl.adaptive import DEFAULT_WEIGHTS, _merge_weights  # noqa: E402
from fpl.player_history import _cache_status, _per90_from_rows  # noqa: E402
from fpl.simulator import simulate_gw, _goals_lambda  # noqa: E402


def _snapshot_df():
    return pd.DataFrame([
        {
            "id": 1, "web_name": "A", "pos": "MID", "proj": 5.5,
            "proj_pre_cal": 6.0, "fdr": 3, "team_short": "AAA",
            "status": "a", "news": "", "chance": 100.0,
            "is_home": True, "n_fixtures": 1,
        },
        {
            "id": 2, "web_name": "B", "pos": "DEF", "proj": None,
            "proj_pre_cal": None, "fdr": 2, "team_short": "BBB",
            "status": "i", "news": "Knee injury", "chance": 0.0,
            "is_home": False, "n_fixtures": 1,
        },
    ])


def test_snapshot_roundtrip_and_deadline(monkeypatch, tmp_path):
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path)
    df = _snapshot_df()
    path = snapshots.save_projection_snapshot(
        9, df, deadline="2030-01-01T00:00:00Z", force=True
    )
    assert path is not None and path.exists()
    latest = snapshots.latest_snapshot(9)
    assert latest is not None
    rows = snapshots.snapshot_rows(latest)
    assert len(rows) == 1  # players without a projection are skipped
    assert rows[0]["web_name"] == "A"
    assert abs(rows[0]["proj_served"] - 5.5) < 1e-9
    assert abs(rows[0]["proj_raw"] - 6.0) < 1e-9

    # Deadline in the past -> no pre-deadline snapshot.
    assert snapshots.pre_deadline_snapshot(9, "2000-01-01T00:00:00Z") is None
    # Deadline in the future -> latest snapshot.
    assert snapshots.pre_deadline_snapshot(9, "2030-01-01T00:00:00Z") is not None


def test_calibration_shrink_apply():
    df = pd.DataFrame({"id": [1], "pos": ["MID"], "proj": [6.0], "n_fixtures": [1]})
    params = {
        "enabled": True,
        "method": "shrink",
        "apply_by_pos": False,
        "global": {"t": 4.0, "f": 0.5, "n": 100},
        "by_pos": {},
    }
    out = calibration.apply(df, params=params)
    # 4 + 0.5 * (6 - 4) = 5
    assert abs(out["proj"].iloc[0] - 5.0) < 1e-9
    assert out["proj_pre_cal"].iloc[0] == 6.0


def test_active_weights_deep_merge():
    base = {"form_w": 0.4, "cs": {"gk": 0.25, "def": 0.25, "mid": 0.10}}
    merged = _merge_weights(base, {"form_w": 0.5, "cs": {"gk": 0.15}})
    assert merged["form_w"] == 0.5
    assert merged["cs"]["gk"] == 0.15
    # Missing keys must not disappear.
    assert merged["cs"]["def"] == 0.25
    assert merged["cs"]["mid"] == 0.10


def test_accuracy_spearman():
    assert accuracy._spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert accuracy._spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert accuracy._spearman([1, 1, 1], [1, 2, 3]) is None


def test_accuracy_price_bucket():
    assert accuracy._price_bucket(45) == "<=4.5m"
    assert accuracy._price_bucket(46) == "4.6-6.0m"
    assert accuracy._price_bucket(80) == "6.1-8.0m"
    assert accuracy._price_bucket(111) == ">11.0m"
    assert accuracy._price_bucket(None) is None


def test_xi_value_captain_bonus():
    rows = (
        [{"id": 1, "pos": "GK", "team": 1}, {"id": 2, "pos": "GK", "team": 2}]
        + [{"id": 10 + i, "pos": "DEF", "team": 3 + i} for i in range(5)]
        + [{"id": 20 + i, "pos": "MID", "team": 8 + i} for i in range(5)]
        + [{"id": 30 + i, "pos": "FWD", "team": 13 + i} for i in range(3)]
    )
    pos_of = {r["id"]: r["pos"] for r in rows}
    values = {r["id"]: float(r["id"]) for r in rows}
    plain = planner.xi_value(list(pos_of), values, pos_of)
    with_cap = planner.xi_value(list(pos_of), values, pos_of, captain_mult=1.0)
    assert with_cap > plain
    # Captain adds exactly one copy of the best player in the selected XI.
    assert 0 < with_cap - plain <= max(values.values())


def test_player_history_cache_status():
    now = time.time()
    fresh = {"ts": now, "rows": [{"gw": 8, "minutes": 90}]}
    assert _cache_status(fresh, current_gw=9) == "fresh"

    stale_gw = {"ts": now, "rows": [{"gw": 5, "minutes": 90}]}
    assert _cache_status(stale_gw, current_gw=9) == "stale_gw"

    too_old = {"ts": now - 40 * 24 * 3600, "rows": [{"gw": 8, "minutes": 90}]}
    assert _cache_status(too_old, current_gw=9) == "too_old"

    assert _cache_status(None, current_gw=9) == "missing"


def test_free_transfers_chip_week_keeps_normal_ft(monkeypatch):
    import fpl.api as api

    monkeypatch.setattr(api, "get_entry_history", lambda team_id: {
        "chips": [{"event": 1, "name": "bboost"}],
        "current": [{"event": 1, "event_transfers": 0, "event_transfers_cost": 0}],
    })
    ft, _ = planner.free_transfers(1)
    # Start with 1, chip week still grants the normal +1.
    assert ft == 2, ft


def test_simulator_does_not_gift_clean_sheets_to_untracked_opponents():
    """A one-team squad must still face the opponent's goal threat.

    Regression test for the bug where an untracked away side had lambda=0 and
    every defender/GK got a guaranteed clean sheet.
    """

    class _GD:
        next_event = {"id": 1}
        teams_by_id = {
            1: {"id": 1, "short_name": "AAA"},
            2: {"id": 2, "short_name": "BBB"},
        }
        team_indices = {
            "_meta": {"L_home": 1.4, "L_away": 1.2},
            1: {"att": 1.0, "gc": 1.0},
            2: {"att": 1.3, "gc": 1.0},
        }

        def fixture_list_for_team_event(self, team_id, event_id):
            if team_id == 1:
                return [{"opponent": 2, "difficulty": 3, "is_home": True}]
            return []

    df = pd.DataFrame([
        {
            "id": 1, "team": 1, "pos": "GK", "web_name": "GK",
            "team_short": "AAA", "pen_order": None, "saves_per_game": 0,
            "xG_per90": 0.0, "xA_per90": 0.0, "minutes": 720, "starts": 8,
            "bonus_per_game": 0.1, "selected_by": 1.0, "price": 50,
            "status": "a", "chance": 100.0, "dc_prob": 0.0,
        },
        {
            "id": 2, "team": 1, "pos": "DEF", "web_name": "DEF",
            "team_short": "AAA", "pen_order": None, "saves_per_game": 0,
            "xG_per90": 0.05, "xA_per90": 0.05, "minutes": 720, "starts": 8,
            "bonus_per_game": 0.2, "selected_by": 1.0, "price": 50,
            "status": "a", "chance": 100.0, "dc_prob": 0.0,
        },
    ])
    rows = df.to_dict("records")
    pts, played, comp = simulate_gw(
        _GD(), df, rows, n=3000, seed=1, return_components=True
    )
    cs_mean = comp[2]["clean_sheet"] / 3000.0
    # With an opponent lambda of 1.3, a clean sheet is roughly 27%; the old
    # bug produced 100% (4.0 CS points per match).
    assert cs_mean < 3.0, cs_mean
    assert float(np.mean(pts[2])) >= 0.0


def test_per90_ignores_short_cameo():
    rows = [
        {"minutes": 90, "xg": 0.20},
        {"minutes": 90, "xg": 0.15},
        {"minutes": 5, "xg": 0.78},  # cameo must not dominate
        {"minutes": 90, "xg": 0.10},
    ]
    rate = _per90_from_rows(rows, "xg")
    assert rate is not None
    assert rate < 0.4, rate


def test_goals_lambda_uses_clamped_dynamic_multiplier():
    class _GD:
        team_indices = {"_meta": {"L_home": 1.4, "L_away": 1.2}}

        def fixture_dyn_mult(self, team_id, opponent_id, is_home):
            return 1.2

    lam = _goals_lambda(_GD(), 1, 2, True)
    assert abs(lam - 1.4 * 1.2) < 1e-9, lam

    class _ExtremeGD(_GD):
        def fixture_dyn_mult(self, team_id, opponent_id, is_home):
            return 10.0

    assert _goals_lambda(_ExtremeGD(), 1, 2, True) == 3.5


def test_bonus_points_are_three_two_one():
    class _GD:
        next_event = {"id": 1}
        teams_by_id = {1: {"short_name": "AAA"}, 2: {"short_name": "BBB"}}
        team_indices = {}

        def fixture_list_for_team_event(self, team_id, event_id):
            return [{
                "opponent": 2 if team_id == 1 else 1,
                "difficulty": 3,
                "is_home": team_id == 1,
            }]

    rows = []
    for team in (1, 2):
        for i in range(5):
            rows.append({
                "id": team * 100 + i, "team": team, "pos": "MID",
                "web_name": f"P{team}{i}", "team_short": "AAA" if team == 1 else "BBB",
                "pen_order": None, "saves_per_game": 0,
                "xG_per90": 0.0, "xA_per90": 0.0,
                "minutes": 720, "starts": 8, "bonus_per_game": 0.5,
                "selected_by": 1.0, "price": 50, "status": "a",
                "chance": 100.0, "dc_prob": 0.0,
            })
    df = pd.DataFrame(rows)
    n = 100
    _pts, _played, comp = simulate_gw(
        _GD(), df, rows, n=n, seed=1, return_components=True
    )
    total_bonus = sum(comp[r["id"]]["bonus"] for r in rows) / n
    assert abs(total_bonus - 6.0) < 1e-9, total_bonus
    assert max(comp[r["id"]]["bonus"] / n for r in rows) <= 3.0


def test_active_weights_ignores_zero_sample(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    import fpl.adaptive as adaptive

    path = Path(tmp_path) / "tuned_weights.json"
    path.write_text(json.dumps({
        "weights": {"form_w": 0.99},
        "metrics": {"enabled": True, "n_samples": 0, "improvement_pct": None},
    }))
    monkeypatch.setattr(adaptive, "WEIGHTS_FILE", path)
    weights = adaptive.get_active_weights()
    assert weights["form_w"] == DEFAULT_WEIGHTS["form_w"]


def _main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            # pytest-style fixtures are not available in the plain runner.
            if "monkeypatch" in fn.__code__.co_varnames or "tmp_path" in fn.__code__.co_varnames:
                import tempfile
                from pathlib import Path

                class _MP:
                    def setattr(self, obj, name, value):
                        setattr(obj, name, value)

                with tempfile.TemporaryDirectory() as td:
                    args = []
                    if "monkeypatch" in fn.__code__.co_varnames:
                        args.append(_MP())
                    if "tmp_path" in fn.__code__.co_varnames:
                        args.append(Path(td))
                    fn(*args)
            else:
                fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests lulus")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
