"""FastAPI backend for the shadcn-style FPL dashboard.

The existing Python model/simulator/planner modules remain the source of
truth.  This API exposes their outputs as JSON to the React frontend.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIST = ROOT / "web" / "dist"

app = FastAPI(title="FPL HQ API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str, ttl: float):
    item = _CACHE.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > ttl:
        return None
    return value


def _cache_set(key: str, value: Any):
    _CACHE[key] = (time.time(), value)
    return value


def _num(value, default=None):
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _clean(value):
    """Recursively convert numpy/pandas values into JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        if hasattr(value, "item"):
            return _clean(value.item())
    except Exception:
        pass
    return str(value)


def _load_core(force: bool = False):
    from fpl.api import get_game_data
    from fpl.model import build_projection_table

    gd = get_game_data(force=force)
    df = build_projection_table(gd)
    return gd, df


def _availability_info(player):
    from fpl.availability import availability

    av = availability(player)
    return {
        "status": av["status"],
        "label": av["label"],
        "status_label": av["status_label"],
        "pct": av["pct"],
        "this_pct": av["this_pct"],
        "next_pct": av["next_pct"],
        "action": av["action"],
        "severity": av["severity"],
        "is_out": av["is_out"],
        "news": av["news"],
        "return_text": av["return_text"],
    }


def _with_past(gd, df):
    """Attach last-season stats for the player table / stars section."""
    cached = _cache_get("paststats_df", 900)
    if cached is not None:
        return cached
    try:
        from fpl.paststats import attach, load as load_past

        out = attach(df, load_past(gd))
    except Exception:
        out = df
    return _cache_set("paststats_df", out)


def _next_fixtures(gd, team_id, n=3):
    """Next N fixtures for a team, ordered by event/kickoff."""
    if team_id is None:
        return []
    current = int(gd.next_event["id"])
    out = []
    for f in gd.fixtures:
        event = f.get("event")
        if not event or int(event) < current:
            continue
        if f.get("team_h") == int(team_id):
            out.append({
                "event": int(event),
                "opponent": gd.teams_by_id[f["team_a"]]["short_name"],
                "fdr": f.get("team_h_difficulty"),
                "is_home": True,
                "kickoff": f.get("kickoff_time"),
            })
        elif f.get("team_a") == int(team_id):
            out.append({
                "event": int(event),
                "opponent": gd.teams_by_id[f["team_h"]]["short_name"],
                "fdr": f.get("team_a_difficulty"),
                "is_home": False,
                "kickoff": f.get("kickoff_time"),
            })
    out.sort(key=lambda r: (r["event"], r.get("kickoff") or ""))
    return _clean(out[:n])


def _player_payload(row, detail: bool = False):
    from fpl.availability import availability

    av = availability(row)
    out = {
        "id": int(row["id"]),
        "name": row.get("web_name"),
        "team": row.get("team_short"),
        "team_name": row.get("team_name"),
        "pos": row.get("pos"),
        "price": _num(row.get("price")),
        "proj": _num(row.get("proj")),
        "ep_next": _num(row.get("ep_next_fpl")),
        "form": _num(row.get("form")),
        "ppg": _num(row.get("ppg")),
        "selected_by": _num(row.get("selected_by")),
        "status": row.get("status"),
        "news": row.get("news") or "",
        "chance": av["pct"],
        "availability": {
            "label": av["label"],
            "pct": av["pct"],
            "is_out": av["is_out"],
            "action": av["action"],
        },
        "fdr": _num(row.get("fdr")),
        "opponent": row.get("opponent_short"),
        "is_home": bool(row.get("is_home")) if row.get("is_home") is not None else None,
        "n_fixtures": int(row.get("n_fixtures") or 1),
        "minutes": _num(row.get("minutes")),
        "starts": _num(row.get("starts")),
        "exp_minutes": _num(row.get("exp_minutes")),
        "xgi90": _num(row.get("xGI_per90")),
        "dc_prob": _num(row.get("dc_prob")),
        "cs_prob": _num(row.get("cs_prob")),
        "last_points": _num(row.get("last_points")),
        "last_ppg": _num(row.get("last_ppg")),
        "last_value": _num(row.get("last_value")),
        "last_starts": _num(row.get("last_starts")),
        "ml_proj": _num(row.get("ml_proj")),
    }
    if detail:
        out.update({
            "xG90": _num(row.get("xG_per90")),
            "xA90": _num(row.get("xA_per90")),
            "bonus_pg": _num(row.get("bonus_per_game")),
            "creativity_pg": _num(row.get("creativity_per_game")),
            "ict_pg": _num(row.get("ict_per_game")),
            "rec_form": _num(row.get("rec_form")),
            "rec_xgi90": _num(row.get("rec_xgi90")),
            "rec_xg90": _num(row.get("rec_xg90")),
            "rec_xa90": _num(row.get("rec_xa90")),
            "rec_dc90": _num(row.get("rec_dc90")),
            "saves_pg": _num(row.get("saves_per_game")),
            "pen_order": row.get("pen_order"),
            "chance_this": _num(row.get("chance_this")),
            "chance_next": _num(row.get("chance_next")),
        })
    return _clean(out)


def _squad_payload(gd, df):
    from fpl.availability import availability
    from fpl.planner import manager_state
    from fpl.simulator import load_saved_squad

    gw = int(gd.next_event["id"])
    state = manager_state(df, current_gw=gw)
    source = "Tim FPL terhubung"
    if state is None:
        rows, _xi, label = load_saved_squad(df)
        if rows is None:
            return {"ids": [], "players": [], "source": label, "bank": 0, "free_transfers": 1, "chips": []}
        source = label
        ids = [int(r["id"]) for r in rows]
        bank = 0.0
        free_transfers = 1
        chips = []
        team_value = round(sum(_num(r.get("price"), 0) for r in rows) / 10.0, 1)
    else:
        rows = state["squad_rows"]
        ids = list(state["squad_ids"])
        bank = round(state["bank"] / 10.0, 1)
        free_transfers = state["free_transfers"]
        chips = (state.get("chips") or {}).get("available_now", [])
        team_value = round(float(state.get("team_value") or 100.0), 1)
        source = f"Tim FPL {state.get('team_name') or state.get('team_id')}"

    players = []
    for r in rows:
        p = _player_payload(r)
        p["status"] = r.get("status")
        p["news"] = r.get("news") or ""
        players.append(p)
    return _clean({
        "ids": ids,
        "players": players,
        "source": source,
        "bank": bank,
        "team_value": team_value,
        "free_transfers": free_transfers,
        "chips": chips,
    })


def _captain_payload(gd, df):
    from fpl.planner import manager_state
    from fpl.simulator import captain_analysis, load_saved_squad, optimal_lineup, reference_xi

    key = f"captain:{gd.next_event['id']}"
    cached = _cache_get(key, 600)
    if cached is not None:
        return cached

    gw = int(gd.next_event["id"])
    state = manager_state(df, current_gw=gw)
    if state:
        rows = state["squad_rows"]
        label = f"Tim FPL {state.get('team_name') or state.get('team_id')}"
    else:
        rows, _old_xi, label = load_saved_squad(df)
        if rows is None:
            rows = reference_xi(df)
            label = "XI referensi"
    # Use the same Auto XI as the dashboard (never the stale saved starters).
    line = optimal_lineup(gd, df, rows, n=400)
    xi_ids = line.get("xi_ids")
    mc = captain_analysis(gd, df, rows, xi_ids=xi_ids, n=900, seed=7)
    out = _clean({
        "source": label,
        "n": mc["n"],
        "xi_ev": mc["xi_ev"],
        "distribution": mc["cap_distribution"],
        "candidates": mc["candidates"][:12],
    })
    return _cache_set(key, out)


def _accuracy_summary():
    cached = _cache_get("accuracy_summary", 900)
    if cached is not None:
        return cached
    try:
        from fpl.accuracy import history

        completed = [h for h in history() if h.get("metrics")]
        if not completed:
            return _cache_set("accuracy_summary", None)
        latest = completed[-1]
        m = latest["metrics"]
        out = {
            "gw": latest["gw"],
            "mae": m.get("mae"),
            "rmse": m.get("rmse"),
            "bias": m.get("bias"),
            "n": m.get("n"),
            "n_gws": len(completed),
            "top10": (m.get("top_k") or {}).get("10"),
            "captain": m.get("captain"),
        }
        return _cache_set("accuracy_summary", _clean(out))
    except Exception:
        return None


def _dashboard_payload(force: bool = False):
    from fpl.action_plan import build_action_plan, confidence_for_captain, confidence_for_transfer, first_transfer
    from fpl.availability import availability
    from fpl.snapshots import freshness

    key = "dashboard"
    if not force:
        cached = _cache_get(key, 600)
        if cached is not None:
            return cached

    gd, df = _load_core(force=force)
    gw = int(gd.next_event["id"])
    payload = build_action_plan(gd, df, gw, n_sim=400, horizon=6)
    state = payload["state"]
    line = payload["line"]
    plan = payload["plan"]
    chips = payload["chips"] if isinstance(payload["chips"], dict) else {}
    chip_calendar = payload.get("chip_calendar") or {}
    cap = line.get("captain") or {}
    vc = line.get("vice") or {}
    cap_dist = line.get("captain_distribution") or {}
    by_id = {int(r["id"]): r for r in df.to_dict("records")}

    first = first_transfer(plan)
    transfer = None
    if first and int(first.get("gw") or 0) == gw:
        t = first["transfers"][0]
        transfer = {
            "headline": f"Jual {t.get('out_name')} → beli {t.get('in_name')}",
            "first_gw": int(first["gw"]),
            "transfers": first["transfers"],
            "hits": int(first.get("hits") or 0),
            "gain": _num(plan.get("gain")),
            "confidence": confidence_for_transfer(plan, state),
            "meaning": (
                f"Gain {plan.get('gain', 0):+.1f} poin / {plan.get('horizon', 6)} GW."
                + (f" Penalti -{first.get('hits', 0)}." if first.get("hits") else " Tanpa penalti.")
            ),
        }
    else:
        nxt = first
        transfer = {
            "headline": "Tidak perlu transfer minggu ini",
            "first_gw": None,
            "transfers": [],
            "hits": 0,
            "gain": _num(plan.get("gain")),
            "confidence": "Tinggi",
            "meaning": (
                f"Rencana berikutnya: GW {nxt['gw']}." if nxt
                else "Tidak ada gain yang cukup aman dalam horizon rencana."
            ),
        }

    alerts = []
    for r in state.get("squad_rows") or []:
        av = availability(r)
        if av["is_out"] or av["pct"] < 100:
            alerts.append({
                "id": int(r["id"]),
                "name": r.get("web_name"),
                "team": r.get("team_short"),
                "status": av["status_label"],
                "label": av["label"],
                "pct": av["pct"],
                "news": av.get("news") or "",
                "action": av.get("action"),
                "is_out": av["is_out"],
            })
    alerts.sort(key=lambda a: (not a["is_out"], a["pct"]))

    chip_gain = 0.0
    chip_label = None
    for key_name, label, threshold in (("TC", "Triple Captain", 4.0), ("BB", "Bench Boost", 4.0),
                                       ("FH", "Free Hit", 6.0), ("WC", "Wildcard", 8.0)):
        c = chips.get(key_name)
        if c and _num(c.get("gain"), 0) >= threshold and _num(c.get("gain"), 0) > chip_gain:
            chip_gain = _num(c.get("gain"), 0)
            chip_label = label
    if chip_label:
        chip = {
            "headline": f"Pertimbangkan {chip_label}",
            "metric": f"+{chip_gain:.1f} poin",
            "meaning": "Gain di atas ambang aman. Cek detail sebelum memakai.",
            "confidence": "Sedang",
            "tone": "warn",
            "available": state.get("chips", {}).get("available_now", []),
        }
    else:
        best = (chip_calendar or {}).get("best") or {}
        tc = best.get("TC")
        chip = {
            "headline": "Simpan chip minggu ini",
            "metric": "Tidak ada chip mendesak",
            "meaning": (
                f"TC terbaik diperkirakan GW {tc['gw']} (+{tc['score']:.1f}). Set pertama hangus GW19."
                if tc else "Belum ada Double/Blank Gameweek yang jelas."
            ),
            "confidence": "Tinggi",
            "tone": "good",
            "available": state.get("chips", {}).get("available_now", []),
        }

    def _xi_payload(items, bench=False):
        out = []
        for p in items:
            pid = int(p["id"])
            row = by_id.get(pid, {})
            out.append({
                "id": pid,
                "name": p.get("web_name"),
                "team": p.get("team_short"),
                "pos": p.get("pos"),
                "price": _num(row.get("price")),
                "proj": _num(p.get("proj")),
                "ev": _num(p.get("ev")),
                "p_play": _num(p.get("p_play")),
                "bench_slot": p.get("bench_slot") if bench else None,
                "status": row.get("status"),
                "news": row.get("news") or "",
                "opponent": row.get("opponent_short"),
                "fdr": _num(row.get("fdr")),
                "is_home": bool(row.get("is_home")) if row.get("is_home") is not None else None,
                "chance": _num(row.get("chance")),
                "next_fixtures": _next_fixtures(gd, row.get("team"), n=3),
            })
        return _clean(out)

    dfp = _with_past(gd, df)
    players_all = dfp.to_dict("records")
    available = [p for p in players_all if p.get("proj") and p["proj"] > 0]
    top_players = [
        _player_payload(r)
        for r in dfp.dropna(subset=["proj"]).nlargest(10, "proj").to_dict("records")
    ]

    # FDR grid + easy fixtures (old Beranda sections).
    fdr_grid = []
    for t in gd.teams_by_id.values():
        fx = gd.fixture_for_team(t["id"])
        fdr_grid.append({
            "team": t["short_name"],
            "team_name": t["name"],
            "opponent": gd.teams_by_id[fx["opponent"]]["short_name"] if fx else "-",
            "fdr": fx["difficulty"] if fx else None,
            "is_home": fx["is_home"] if fx else None,
        })
    fdr_grid.sort(key=lambda r: (r["fdr"] is None, r["fdr"] or 9, r["team"]))

    easy_players = [
        _player_payload(r)
        for r in dfp.dropna(subset=["proj"])
        .query("fdr <= 2 and chance >= 75")
        .nlargest(10, "proj")
        .to_dict("records")
    ] if "chance" in dfp.columns else []

    last_stars = [
        {**_player_payload(r), "last_points": _num(r.get("last_points")), "last_ppg": _num(r.get("last_ppg"))}
        for r in dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0)].nlargest(10, "last_points").to_dict("records")
    ] if "last_points" in dfp.columns else []

    last_value = [
        {**_player_payload(r), "last_value": _num(r.get("last_value"))}
        for r in dfp[(dfp["last_starts"] >= 15) & (dfp["last_points"] > 0) & (dfp["price"] <= 110)].nlargest(8, "last_value").to_dict("records")
    ] if "last_value" in dfp.columns else []

    # Old rotation-risk and bench sections.
    try:
        from fpl.optimizer import rotation_risk

        risks = rotation_risk(players_all)[:10]
        rotation_risks = [{
            "name": r["player"].get("web_name"),
            "team": r["player"].get("team_short"),
            "pos": r["player"].get("pos"),
            "reasons": r["reasons"],
            "severity": r["severity"],
            "proj": _num(r["player"].get("proj")),
        } for r in risks]
    except Exception:
        rotation_risks = []

    # Old Kapten & Transfer market sections.
    try:
        from fpl.optimizer import overpriced_players, risk_players, value_picks
        from fpl.transfer import differential_picks, fixture_ticker_table

        value = [
            {**_player_payload(p), "value": _num(p.get("value"))}
            for p in value_picks(available, n=20)
        ]
        diffs = [
            {**_player_payload(p), "diff_score": _num(p.get("diff_score"))}
            for p in differential_picks(available, ownership_threshold=5.0, min_proj=2.0, n=10)
        ]
        risky = _clean([_player_payload(p) for p in risk_players(players_all, n=10)])
        over = _clean([_player_payload(p) for p in overpriced_players(players_all, n=10)])
        ticker_rows, ticker_gw = fixture_ticker_table(gd, n_gws=6)
        market = {
            "value_picks": value,
            "differentials": diffs,
            "risk_players": risky,
            "overpriced": over,
            "ticker": ticker_rows,
            "ticker_gw": ticker_gw,
        }
    except Exception:
        market = {}

    # Old injury-aware transfer suggestions.
    try:
        from fpl.horizon import player_gw_projections
        from fpl.transfer import injury_transfer_suggestions

        gw_projs = player_gw_projections(dfp, gd, horizon=3)
        raw_injuries = injury_transfer_suggestions(
            state.get("squad_rows") or [],
            players_all,
            gw_projs,
            bank=int(state.get("bank") or 0),
            horizon=3,
            sell_prices=state.get("sell_prices") or {},
            min_in_chance=0,
        )
        injury_suggestions = [
            {
                **s,
                "player": _player_payload(s["player"]),
                "replacement": _player_payload(s["replacement"]) if s.get("replacement") else None,
            }
            for s in raw_injuries
        ]
    except Exception:
        injury_suggestions = []

    snap = freshness(gw)
    try:
        hist_fresh = int((df["hist_status"] == "fresh").sum())
    except Exception:
        hist_fresh = 0

    try:
        from fpl.decisions import save_recommendation

        chip_rec = {
            "headline": chip.get("headline"),
            "metric": chip.get("metric"),
            "available": chip.get("available"),
            "gains": {
                k: (chips.get(k) or {}).get("gain")
                for k in ("TC", "BB", "FH", "WC")
                if isinstance(chips, dict) and isinstance(chips.get(k), dict)
            },
        }
        save_recommendation(
            gw,
            gd.next_event.get("deadline_time"),
            captain=cap,
            transfer=transfer if transfer and transfer.get("transfers") else None,
            chips=chip_rec,
            lineup=line,
            source=payload.get("source") or "dashboard",
        )
    except Exception:
        # Decision tracking must never block the dashboard.
        pass

    result = _clean({
        "gw": {
            "id": gw,
            "name": gd.next_event.get("name", f"Gameweek {gw}"),
            "deadline": gd.next_event.get("deadline_time"),
            "average_score": gd.next_event.get("average_entry_score"),
        },
        "updated_at": time.time(),
        "source": payload.get("source"),
        "captain": {
            "id": int(cap.get("id")) if cap.get("id") is not None else None,
            "name": cap.get("web_name"),
            "team": cap.get("team_short"),
            "pos": cap.get("pos"),
            "price": _num(by_id.get(int(cap["id"]), {}).get("price")) if cap.get("id") is not None else None,
            "proj": _num(cap.get("proj")),
            "ev": _num(cap.get("model_points", cap.get("ev_captain"))),
            "sim_ev": _num(cap.get("ev_captain")),
            "ev_no_vc": _num(cap.get("ev_no_vc")),
            "p_play": _num(cap.get("p_play")),
            "p_blank": _num(cap.get("p_blank")),
            "p_haul": _num(cap.get("p_haul")),
            "p10": _num(cap.get("p10", cap_dist.get("p10"))),
            "p50": _num(cap.get("p50", cap_dist.get("p50"))),
            "p90": _num(cap.get("p90", cap_dist.get("p90"))),
            "selected_by": _num(by_id.get(int(cap["id"]), {}).get("selected_by")) if cap.get("id") is not None else None,
            "confidence": confidence_for_captain(line),
            "vice": vc.get("web_name"),
        },
        "transfer": transfer,
        "chip": chip,
        "alerts": alerts,
        "xi": _xi_payload(line.get("xi", [])),
        "bench": _xi_payload(line.get("bench", []), bench=True),
        "line": _clean({
            "ev": line.get("ev"),
            "ev_naive": line.get("ev_naive"),
            "formation": line.get("formation"),
            "n": line.get("n"),
        }),
        "plan": _clean(plan),
        "chips": _clean(chips),
        "chip_calendar": _clean(chip_calendar),
        "squad": _squad_payload(gd, df),
        "top_players": top_players,
        "easy_players": easy_players,
        "fdr_grid": fdr_grid,
        "last_stars": last_stars,
        "last_value": last_value,
        "rotation_risks": rotation_risks,
        "market": market,
        "injury_suggestions": injury_suggestions,
        "accuracy_summary": _accuracy_summary(),
        "data_health": {
            "history_fresh": hist_fresh,
            "history_total": int(len(df)),
            "snapshot_available": snap.get("available", False),
            "snapshot_age_minutes": snap.get("age_minutes"),
        },
    })
    return _cache_set(key, result)


@app.get("/api/health")
def health():
    return {"ok": True, "time": time.time()}


@app.get("/api/dashboard")
def dashboard(force: bool = False):
    try:
        return _dashboard_payload(force=force)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal membangun dashboard: {exc}") from exc


@app.get("/api/players")
def players():
    cached = _cache_get("players", 600)
    if cached is not None:
        return cached
    try:
        _gd, df = _load_core()
        dfp = _with_past(_gd, df)
        rows = dfp.sort_values("proj", ascending=False, na_position="last").to_dict("records")
        data = [_player_payload(r, detail=True) for r in rows]
        return _cache_set("players", data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil pemain: {exc}") from exc


@app.get("/api/captain")
def captain():
    try:
        gd, df = _load_core()
        return _captain_payload(gd, df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal simulasi kapten: {exc}") from exc


@app.get("/api/performance")
def performance():
    cached = _cache_get("performance", 900)
    if cached is not None:
        return cached
    try:
        from fpl.accuracy import history
        from fpl.backtest import compare_baselines
        from fpl.decisions import decision_summary

        hist = history()
        out = _clean({
            "history": hist,
            "baselines": compare_baselines(),
            "decisions": decision_summary(),
        })
        return _cache_set("performance", out)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil performa: {exc}") from exc


@app.get("/api/history")
def history():
    cached = _cache_get("history", 300)
    if cached is not None:
        return cached
    try:
        from fpl.gw_history import chip_impact, fetch_season_history
        from fpl.team import get_saved_team_id

        team_id = get_saved_team_id()
        if not team_id:
            return _cache_set("history", {"available": False, "message": "Tim FPL belum tersinkron."})
        data = fetch_season_history(int(team_id))
        out = _clean({
            "available": True,
            "team_id": team_id,
            "team_name": data.get("team_name"),
            "manager_name": data.get("manager_name"),
            "overall_points": data.get("overall_points"),
            "overall_rank": data.get("overall_rank"),
            "gw_results": data.get("gw_results", []),
            "chips_played": data.get("chips_played", []),
            "chip_impact": chip_impact(data),
            "best_gw": data.get("best_gw"),
            "worst_gw": data.get("worst_gw"),
            "total_hits": data.get("total_hits"),
            "total_bench_pts": data.get("total_bench_pts"),
        })
        return _cache_set("history", out)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil riwayat: {exc}") from exc


@app.get("/api/squad-insights")
def squad_insights():
    cached = _cache_get("squad_insights", 600)
    if cached is not None:
        return cached
    try:
        from fpl.horizon import player_gw_projections, risky_players, squad_plan
        from fpl.planner import manager_state
        from fpl.simulator import load_saved_squad
        from fpl.transfer import multi_gw_transfers

        gd, df = _load_core()
        dfp = _with_past(gd, df)
        state = manager_state(dfp, current_gw=int(gd.next_event["id"]))
        if state:
            rows = state["squad_rows"]
            bank = int(state["bank"])
            sell = state["sell_prices"]
            source = f"Tim FPL {state.get('team_name') or state.get('team_id')}"
        else:
            rows, _xi, label = load_saved_squad(dfp)
            if rows is None:
                return _cache_set("squad_insights", {"available": False, "message": label})
            bank = 0
            sell = {}
            source = label
        players = dfp.to_dict("records")
        gw_projs = player_gw_projections(dfp, gd, horizon=3)
        multi = multi_gw_transfers(rows, players, gw_projs, bank=bank, horizon=3, sell_prices=sell)
        single = multi_gw_transfers(rows, players, gw_projs, bank=bank, horizon=1, sell_prices=sell)
        plans = squad_plan(rows, gw_projs, horizon=3)
        risky = risky_players(rows, gw_projs, horizon=3)
        out = _clean({
            "available": True,
            "source": source,
            "bank": round(bank / 10.0, 1),
            "multi": multi[:5],
            "single": single[:3],
            "plans": plans,
            "risky": [{"player": _player_payload(p), "future": v} for p, v in risky],
        })
        return _cache_set("squad_insights", out)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil insight skuad: {exc}") from exc


@app.get("/api/lab")
def lab():
    cached = _cache_get("lab", 600)
    if cached is not None:
        return cached
    try:
        from fpl import calibration
        from fpl.adaptive import load_tuned_weights
        from fpl.ml_model import model_status

        _gd, df = _load_core()
        from fpl.action_plan import build_action_plan

        payload = build_action_plan(_gd, df, int(_gd.next_event["id"]), n_sim=150, horizon=4)
        out = _clean({
            "chip_calendar": payload.get("chip_calendar"),
            "chips": payload.get("chips"),
            "calibration": calibration.status(),
            "ml": model_status(),
            "adaptive": load_tuned_weights(),
            "data_health": {
                "history_fresh": int((df["hist_status"] == "fresh").sum()) if "hist_status" in df else 0,
                "history_total": int(len(df)),
            },
        })
        return _cache_set("lab", out)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil lab: {exc}") from exc


class SquadBody(BaseModel):
    ids: list[int] = Field(..., min_length=15, max_length=15)
    budget: Optional[int] = Field(default=None, ge=1000, le=2000)


@app.get("/api/squad")
def get_squad():
    try:
        gd, df = _load_core()
        return _squad_payload(gd, df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil skuad: {exc}") from exc


@app.post("/api/squad")
def save_squad(body: SquadBody):
    try:
        import json

        from fpl.validation import validate_squad

        _gd, df = _load_core()
        by_id = {int(r["id"]): r for r in df.to_dict("records")}
        rows = [by_id[i] for i in body.ids if i in by_id]
        if len(rows) != 15:
            raise HTTPException(status_code=400, detail="Ada pemain yang tidak ditemukan.")
        errors = validate_squad(rows, budget=int(body.budget or 1000))
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        (DATA_DIR / "squad.json").write_text(json.dumps([int(i) for i in body.ids]))
        # Keep the connected-manager view in sync with manual edits.  We only
        # change the 15-player pool; bank/FT/sell prices remain from the last
        # FPL sync.
        try:
            manager_file = DATA_DIR / "manager.json"
            if manager_file.exists():
                manager = json.loads(manager_file.read_text())
                manager["squad_ids"] = [int(i) for i in body.ids]
                manager["synced_at"] = time.time()
                manager_file.write_text(json.dumps(manager, indent=2))
        except Exception:
            pass
        _CACHE.clear()
        return {"ok": True, "ids": body.ids}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan skuad: {exc}") from exc


@app.post("/api/refresh")
def refresh():
    _CACHE.clear()
    try:
        from fpl.api import clear_cache

        clear_cache()
    except Exception:
        pass
    return {"ok": True, "time": time.time()}


if WEB_DIST.exists():
    assets = WEB_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = WEB_DIST / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")
