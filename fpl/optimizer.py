from collections import Counter
from itertools import combinations

from .utils import STATUS_LABELS, fmt_price, fdr_badge, home_away_badge, pos_badge, status_badge

FORMATIONS = []
for d in (3, 4, 5):
    for m in (2, 3, 4, 5):
        f = 10 - d - m
        if 1 <= f <= 3:
            FORMATIONS.append((d, m, f))


def _valid_clubs(xi):
    return max(Counter(p["team"] for p in xi).values()) <= 3


def best_xi(squad):
    by_pos = {p: [x for x in squad if x["pos"] == p] for p in ("GK", "DEF", "MID", "FWD")}
    if (
        len(by_pos["GK"]) < 1
        or len(by_pos["DEF"]) < 3
        or len(by_pos["MID"]) < 2
        or len(by_pos["FWD"]) < 1
        or len(squad) != 15
    ):
        return None
    best = None
    for nd, nm, nf in FORMATIONS:
        if len(by_pos["DEF"]) < nd or len(by_pos["MID"]) < nm or len(by_pos["FWD"]) < nf:
            continue
        for gk in combinations(by_pos["GK"], 1):
            for defs in combinations(by_pos["DEF"], nd):
                for mids in combinations(by_pos["MID"], nm):
                    for fwds in combinations(by_pos["FWD"], nf):
                        xi = gk + defs + mids + fwds
                        if not _valid_clubs(xi):
                            continue
                        total = sum(x["proj"] for x in xi)
                        if best is None or total > best["total"]:
                            best = {"xi": xi, "total": round(total, 2), "formation": (nd, nm, nf)}
    if best is None:
        return None
    xi = best["xi"]
    picked = {p["id"] for p in xi}
    bench = sorted([p for p in squad if p["id"] not in picked], key=lambda p: p["proj"], reverse=True)
    ordered = sorted(xi, key=lambda p: p["proj"], reverse=True)

    # Optimize bench order using FPL auto-sub rules
    bench = ordered_bench(bench)

    return {
        "xi": xi,
        "bench": bench,
        "total": best["total"],
        "formation": best["formation"],
        "captain": ordered[0] if ordered else None,
        "vice": ordered[1] if len(ordered) > 1 else None,
    }


def ordered_bench(bench):
    """Order bench players following FPL auto-sub rules for maximum points safety.

    FPL auto-sub rules:
    - Bench position 1 (first sub) is used first if a starter doesn't play
    - GK must be in bench position 4 (only used if starting GK doesn't play)
    - Outfield bench players are ordered by projected points (highest first)

    This ensures the highest-projected bench player gets subbed in first.
    """
    if not bench:
        return bench

    bench_gk = [p for p in bench if p["pos"] == "GK"]
    bench_outfield = [p for p in bench if p["pos"] != "GK"]

    # Sort outfield by projection descending (best first = first to be auto-subbed)
    bench_outfield.sort(key=lambda p: p.get("proj", 0), reverse=True)

    # FPL rule: GK goes to position 4 (last), outfield ordered by projection
    return bench_outfield + bench_gk


def rotation_risk(squad, threshold=75):
    """Identify players in the squad who have high rotation risk.

    Rotation risk is determined by:
    1. Minutes per start < threshold (default 75 minutes)
    2. Status is 'doubtful' (d)
    3. Low chance of playing (< 75%)

    Returns: list of dicts with player info and risk reason.
    """
    risks = []
    for p in squad:
        reasons = []
        mps = p.get("minutes_per_start", 0)
        starts = p.get("starts", 0)
        chance = p.get("chance")
        status = p.get("status", "a")

        # Only flag rotation if we have enough data (at least 1 start)
        if starts > 0 and mps > 0 and mps < threshold:
            reasons.append(f"rata-rata {mps:.0f} mnt/start (risiko rotasi)")

        if status == "d":
            reasons.append("status: diragukan")

        if chance is not None:
            chance_val = float(chance)
            if chance_val < 75:
                reasons.append(f"peluang main {chance_val:.0f}%")

        if reasons:
            risks.append({
                "player": p,
                "reasons": reasons,
                "severity": "high" if len(reasons) >= 2 or (chance is not None and float(chance) < 50) else "medium",
            })

    risks.sort(key=lambda r: (0 if r["severity"] == "high" else 1, r["player"].get("proj", 0)))
    return risks


def suggest_transfers(squad, pool, bank):
    squad_ids = {p["id"] for p in squad}
    by_pos = {pos: [p for p in pool if p["pos"] == pos and p["proj"] > 0] for pos in ("GK", "DEF", "MID", "FWD")}
    candidates = []
    for p in squad:
        budget = p["price"] + bank + 0.5
        reps = [
            q
            for q in by_pos[p["pos"]]
            if q["id"] not in squad_ids and q["price"] <= budget and q["proj"] > p["proj"]
        ]
        reps.sort(key=lambda q: q["proj"], reverse=True)
        top3 = reps[:3]
        if top3:
            candidates.append(
                {
                    "player": p,
                    "reps": top3,
                    "gain": round(top3[0]["proj"] - p["proj"], 2),
                }
            )
    candidates.sort(key=lambda c: c["gain"], reverse=True)
    return candidates


def value_picks(players, n=15):
    out = []
    for p in players:
        if p["proj"] <= 0:
            continue
        out.append({**p, "value": round(p["proj"] / max(p["price"] / 10, 0.1), 2)})
    out.sort(key=lambda p: p["value"], reverse=True)
    return out[:n]


def risk_players(players, n=15):
    risky = []
    for p in players:
        chance = p.get("chance")
        if chance is not None and float(chance) < 50:
            risky.append(p)
        elif p.get("status") in ("i", "u", "n", "d") and p["selected_by"] >= 1:
            risky.append(p)
    risky.sort(key=lambda p: p["selected_by"], reverse=True)
    return risky[:n]


def overpriced_players(players, n=15):
    out = [p for p in players if p["price"] >= 70 and p["proj"] > 0 and p["proj"] < 2.5]
    out.sort(key=lambda p: p["price"], reverse=True)
    return out[:n]


def player_display(p):
    return f"{p['web_name']} ({p['team_short']}, {pos_badge(p['pos'])}, {fmt_price(p['price'])}, proyeksi {p['proj']:.1f})"


def _chance_pct(p):
    """Chance as percent 0-100 (handles raw percent or 0-1 fraction)."""
    c = p.get("chance")
    if c is None:
        return None
    try:
        c = float(c)
    except (TypeError, ValueError):
        return None
    import math
    if math.isnan(c):
        return None
    return c if c > 1 else c * 100.0


def fixture_line(p):
    parts = []
    if p.get("opponent_short"):
        parts.append(f"vs {p['opponent_short']} {home_away_badge(bool(p.get('is_home')))}")
        parts.append(fdr_badge(p.get("fdr")))
    chance_pct = _chance_pct(p)
    if chance_pct is not None and chance_pct < 100:
        parts.append(f"peluang main {chance_pct:.0f}%")
    parts.append(status_badge(p.get("status", "a")))
    return " | ".join(parts) if parts else "-"


def projection_explanation(p):
    n_fx = int(p.get("n_fixtures") or 1)
    dgw = " (DGW — 2 laga!)" if n_fx >= 2 else ""
    lines = [
        f"Base signal (0.40×form {p.get('form', 0):.2f} + 0.20×ppg {p.get('ppg', 0):.2f} + 0.25×xGI {p.get('xgi_signal', 0):.2f} + 0.15×ICT {p.get('ict_signal', 0):.2f}) = {p.get('own', 0):.2f}",
        f"CS probability = {p.get('cs_prob', 0):.1%} (bonus tergantung posisi)",
        f"Threat score (normalized) = {p.get('threat_norm', 0):.3f}",
        f"Bonus tendency (normalized) = {p.get('bonus_norm', 0):.3f}",
        f"Creativity score (normalized) = {p.get('creativity_norm', 0):.3f}",
        f"Minutes consistency = ×{p.get('minutes_factor', 1.0):.2f}",
        f"Faktor lawan (FDR {p.get('fdr', '-')}) = ×{p.get('fixture_mult', 1.0):.3f}",
        f"Koreksi kekuatan tim dinamis = ×{p.get('dyn_mult', 1.0):.3f}" if p.get("dyn_mult") is not None else None,
        f"Kandang/tandang = ×{p.get('home_mult', 1.0):.2f}",
        f"Peluang bermain = {chance_pct:.0f}% (faktor ×{chance_pct / 100:.2f})" if (chance_pct := _chance_pct(p)) is not None else None,
        f"Proyeksi FPL (ep_next) = {p.get('ep_next_fpl', 0):.2f}",
        f"Jumlah laga = {n_fx}{dgw}" if n_fx >= 2 else None,
        f"Bobot: 65% model sendiri + 25% ep_next + 10% safety",
        f"Perkiraan akhir = {p.get('proj', 0):.2f} poin",
    ]
    return "\n".join(line for line in lines if line)


