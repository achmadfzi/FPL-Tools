"""Core tests for the FPL toolkit — runnable with plain Python or pytest.

    .venv/bin/python tests/test_core.py
    # or: .venv/bin/pytest tests/test_core.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fpl import calibration, defcon, planner  # noqa: E402
from fpl.simulator import autosub_points, _lineup_candidates  # noqa: E402


# ---------------------------------------------------------------------------
# Auto-sub rules
# ---------------------------------------------------------------------------


def _mk_player(pid, pos, team):
    return {"id": pid, "pos": pos, "team": team, "proj": 1.0, "price": 45,
            "web_name": f"P{pid}", "team_short": f"T{team}"}


def test_autosub_gk_replacement():
    # 15 players: 2 GK, 5 DEF, 5 MID, 3 FWD
    rows = (
        [_mk_player(1, "GK", 1), _mk_player(2, "GK", 2)]
        + [_mk_player(10 + i, "DEF", 3) for i in range(5)]
        + [_mk_player(20 + i, "MID", 4) for i in range(5)]
        + [_mk_player(30 + i, "FWD", 5) for i in range(3)]
    )
    pos_of = [r["pos"] for r in rows]
    n = 2
    P = np.zeros((n, 15))
    PL = np.ones((n, 15), dtype=bool)
    # starter GK (col 0) is out; bench GK (col 1) plays and scores 6
    PL[:, 0] = False
    P[:, 1] = 6.0
    # XI: GK0 + all 5 DEF + 3 MID (10,20,21... keep formation 4-4-2 style)
    xi = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13]   # 1GK 5DEF 4MID 1FWD -> invalid (1 FWD ok, 4 MID ok)
    bench = [1, 11, 12, 14]
    total = autosub_points(P, PL, xi, bench, pos_of)
    # bench GK must replace the blank starter GK
    assert np.allclose(total, 6.0), total


def test_autosub_outfield_order_and_formation():
    rows = (
        [_mk_player(1, "GK", 1), _mk_player(2, "GK", 2)]
        + [_mk_player(10 + i, "DEF", 3) for i in range(5)]
        + [_mk_player(20 + i, "MID", 4) for i in range(5)]
        + [_mk_player(30 + i, "FWD", 5) for i in range(3)]
    )
    pos_of = [r["pos"] for r in rows]
    n = 3
    P = np.zeros((n, 15))
    PL = np.ones((n, 15), dtype=bool)
    # Formation 3-4-3: cols: GK0, DEF 2,3,4, MID 7,8,9,10, FWD 12,13,14
    xi = [0, 2, 3, 4, 7, 8, 9, 10, 12, 13, 14]
    bench = [1, 5, 6, 11]  # DEF5, DEF6, MID11, GK1
    # One DEF starter (col 2) blanks in every iteration.
    PL[:, 2] = False
    P[:, 5] = 4.0   # bench DEF scores
    P[:, 6] = 9.0   # another bench DEF scores more but comes later
    P[:, 11] = 7.0  # bench MID (entering for DEF would break 3-4-3 min DEF)
    total = autosub_points(P, PL, xi, bench, pos_of)
    # First sub (bench order 5 before 6): DEF5 enters for blank DEF2 -> +4.
    assert np.allclose(total, 4.0), total


def test_autosub_no_sub_when_played():
    rows = (
        [_mk_player(1, "GK", 1), _mk_player(2, "GK", 2)]
        + [_mk_player(10 + i, "DEF", 3) for i in range(5)]
        + [_mk_player(20 + i, "MID", 4) for i in range(5)]
        + [_mk_player(30 + i, "FWD", 5) for i in range(3)]
    )
    pos_of = [r["pos"] for r in rows]
    P = np.ones((1, 15)) * 2.0
    PL = np.ones((1, 15), dtype=bool)
    xi = [0, 2, 3, 4, 7, 8, 9, 10, 12, 13, 14]
    bench = [1, 5, 6, 11]
    total = autosub_points(P, PL, xi, bench, pos_of)
    assert np.allclose(total, 22.0), total  # 11 players x 2


# ---------------------------------------------------------------------------
# DefCon probability
# ---------------------------------------------------------------------------


def test_defcon_probability_bounds():
    assert defcon.hit_probability("GK", 8, 1, 90) == 0.0
    assert defcon.hit_probability("DEF", 0, 1, 90) == 0.0
    p_low = defcon.hit_probability("DEF", 8, 8.0, 90)    # ~7 CBIT/90
    p_high = defcon.hit_probability("DEF", 8, 4.0, 90)   # ~16 CBIT/90
    assert 0.0 <= p_low < p_high <= 0.90
    # No minutes -> no DefCon
    assert defcon.hit_probability("DEF", 8, 4.0, 0) == 0.0


def test_defcon_thresholds():
    # Same rate, higher threshold for MID/FWD than DEF -> lower probability.
    p_def = defcon.hit_probability("DEF", 10, 10.0, 90)
    p_mid = defcon.hit_probability("MID", 10, 10.0, 90)
    assert p_def > p_mid


# ---------------------------------------------------------------------------
# Planner helpers
# ---------------------------------------------------------------------------


def test_selling_price_rules():
    # Profit: half of the profit is taken by FPL, floored.
    assert planner.selling_price(50, 55) == 52   # +5 -> +2
    assert planner.selling_price(50, 51) == 50   # +1 -> +0
    # Loss: sell at current price.
    assert planner.selling_price(60, 55) == 55
    assert planner.selling_price(50, 50) == 50


def test_xi_value_matches_bruteforce():
    import itertools

    rng = np.random.default_rng(3)
    for _ in range(5):
        rows = (
            [_mk_player(1, "GK", 1), _mk_player(2, "GK", 2)]
            + [_mk_player(10 + i, "DEF", 3 + (i % 3)) for i in range(5)]
            + [_mk_player(20 + i, "MID", 4 + (i % 3)) for i in range(5)]
            + [_mk_player(30 + i, "FWD", 5 + (i % 2)) for i in range(3)]
        )
        pos_of = {r["id"]: r["pos"] for r in rows}
        values = {r["id"]: float(rng.uniform(0, 10)) for r in rows}
        gk = [r["id"] for r in rows if r["pos"] == "GK"]
        defs = [r["id"] for r in rows if r["pos"] == "DEF"]
        mids = [r["id"] for r in rows if r["pos"] == "MID"]
        fwds = [r["id"] for r in rows if r["pos"] == "FWD"]
        best = 0.0
        for nd in range(3, 6):
            for nm in range(2, 6):
                nf = 10 - nd - nm
                if not (1 <= nf <= 3):
                    continue
                for d in itertools.combinations(defs, nd):
                    for m in itertools.combinations(mids, nm):
                        for f in itertools.combinations(fwds, nf):
                            tot = (max(values[g] for g in gk)
                                   + sum(values[x] for x in d + m + f))
                            best = max(best, tot)
        got = planner.xi_value(list(pos_of), values, pos_of)
        assert abs(got - best) < 1e-9, (got, best)


def test_lineup_candidates_valid_formations():
    rows = (
        [_mk_player(1, "GK", 1), _mk_player(2, "GK", 2)]
        + [_mk_player(10 + i, "DEF", 3 + i) for i in range(5)]
        + [_mk_player(20 + i, "MID", 8 + i) for i in range(5)]
        + [_mk_player(30 + i, "FWD", 13 + i) for i in range(3)]
    )
    cands = _lineup_candidates(rows)
    assert len(cands) == 550  # 2 GK x 275 combos, no club filtering needed
    for c in cands:
        assert len(c["xi"]) == 11 and len(c["bench"]) == 4
        d = sum(1 for i in c["xi"] if rows[i]["pos"] == "DEF")
        m = sum(1 for i in c["xi"] if rows[i]["pos"] == "MID")
        f = sum(1 for i in c["xi"] if rows[i]["pos"] == "FWD")
        assert 3 <= d <= 5 and 2 <= m <= 5 and 1 <= f <= 3


def test_club_limit_filters_candidates():
    rows = (
        [_mk_player(1, "GK", 1), _mk_player(2, "GK", 2)]
        + [_mk_player(10 + i, "DEF", 3) for i in range(4)] + [_mk_player(14, "DEF", 4)]
        + [_mk_player(20 + i, "MID", 4) for i in range(5)]
        + [_mk_player(30 + i, "FWD", 5) for i in range(3)]
    )
    # team 4 has 6 players -> any 5-DEF XI must break the 3-per-club rule
    # when it includes >3 from team 4; check that candidates never do.
    clinfo = {r["id"]: r["team"] for r in rows}
    cands = _lineup_candidates(rows)
    for c in cands:
        from collections import Counter
        cnt = Counter(clinfo[rows[i]["id"]] for i in c["xi"])
        assert max(cnt.values()) <= 3


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def test_calibration_fit_recovers_linear_map():
    pairs = [{"proj": float(x), "actual": 0.8 * x + 0.5} for x in range(1, 80)]
    # Without shrinkage the exact line is recovered (returns (a, b)).
    a, b = calibration._fit_linear(pairs, k=0)
    assert abs(b - 0.8) < 1e-6, b
    assert abs(a - 0.5) < 1e-6, a
    # With shrinkage the intercept is pulled toward the identity at the
    # sample mean (predictions move away from the raw line toward y = x).
    a_s, b_s = calibration._fit_linear(pairs, k=60)
    pred_raw = a + b * 40.0
    pred_shrunk = a_s + b_s * 40.0
    assert pred_shrunk > pred_raw  # pulled up toward identity (40)


def test_calibration_apply_disabled_is_noop():
    import pandas as pd

    df = pd.DataFrame({"id": [1], "pos": ["MID"], "proj": [5.0], "n_fixtures": [1]})
    out = calibration.apply(df, params={"enabled": False})
    assert "proj_cal" not in out.columns
    assert out["proj"].iloc[0] == 5.0


def test_calibration_apply_enabled_replaces_proj():
    import pandas as pd

    params = {"enabled": True, "global": {"a": 0.5, "b": 0.5, "n": 100}, "by_pos": {}}
    df = pd.DataFrame({"id": [1], "pos": ["MID"], "proj": [6.0], "n_fixtures": [1]})
    out = calibration.apply(df, params=params)
    assert abs(out["proj"].iloc[0] - 3.5) < 1e-6
    assert out["proj_pre_cal"].iloc[0] == 6.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
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
