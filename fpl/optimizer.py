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
    return {
        "xi": xi,
        "bench": bench,
        "total": best["total"],
        "formation": best["formation"],
        "captain": ordered[0] if ordered else None,
        "vice": ordered[1] if len(ordered) > 1 else None,
    }


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


def fixture_line(p):
    parts = []
    if p.get("opponent_short"):
        parts.append(f"vs {p['opponent_short']} {home_away_badge(bool(p.get('is_home')))}")
        parts.append(fdr_badge(p.get("fdr")))
    if p.get("chance") is not None and float(p.get("chance", 1)) < 100:
        parts.append(f"peluang main {float(p['chance']) * 100:.0f}%")
    parts.append(status_badge(p.get("status", "a")))
    return " | ".join(parts) if parts else "-"


def projection_explanation(p):
    lines = [
        f"Estimasi dasar (0.6×form {p.get('form', 0):.2f} + 0.4×ppg {p.get('ppg', 0):.2f}) = {p.get('own', 0):.2f}",
        f"Faktor lawan (FDR {p.get('fdr', '-')}) = ×{p.get('fixture_mult', '-')}",
        f"Kandang/tandang = ×{p.get('home_mult', '-')}",
        f"Peluang bermain = ×{float(p.get('chance', 1)):.0%}" if p.get("chance") is not None else None,
        f"Proyeksi FPL (ep_next) = {p.get('ep_next_fpl', 0):.2f}",
        f"Perkiraan akhir = {p.get('proj', 0):.2f} poin",
    ]
    return "\n".join(line for line in lines if line)
