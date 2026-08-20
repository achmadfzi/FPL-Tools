import json
from collections import Counter

from fpl.api import DATA_DIR, clear_cache, get_game_data
from fpl.model import build_projection_table
from fpl.optimizer import best_xi
from fpl.solver import best_entry, dp_select, pareto_add
from fpl.utils import fmt_price
from fpl.validation import BUDGET, NEED, validate_squad

POS_ORDER = ["GK", "DEF", "MID", "FWD"]


def outfield_candidates(df, gk_clubs, forced_ids):
    forced_by_club = Counter()
    if forced_ids:
        for pid in forced_ids:
            row = df[df["id"] == pid]
            if len(row):
                forced_by_club[int(row.iloc[0]["team"])] += 1
    per_club = {}
    for p in df[df["pos"].isin(["DEF", "MID", "FWD"])].to_dict("records"):
        if p["id"] in forced_ids:
            continue
        club = int(p["team"])
        limit = 3 - gk_clubs.get(club, 0) - forced_by_club.get(club, 0)
        if limit <= 0:
            continue
        per_club.setdefault(club, []).append(p)
    out = []
    for club, lst in per_club.items():
        limit = 3 - gk_clubs.get(club, 0) - forced_by_club.get(club, 0)
        lst.sort(key=lambda p: p["proj"], reverse=True)
        out.extend(lst[:limit])
    return out


def solve(gd, df, forced):
    from itertools import combinations

    forced_ids = [p["id"] for p in forced]
    forced_by_club = Counter()
    for pid in forced_ids:
        row = df[df["id"] == pid]
        if len(row):
            forced_by_club[int(row.iloc[0]["team"])] += 1
    gks = df[df["pos"] == "GK"].sort_values("proj", ascending=False).head(12).to_dict("records")

    cands = outfield_candidates(df, {}, forced_ids)
    cand_map = {p["id"]: p for p in cands}
    all_by_id = {int(p["id"]): p for p in df.to_dict("records")}
    entries = dp_select(cands, forced, BUDGET)

    club_cache = {}

    def club_counts(e):
        key = e["path"]
        if key not in club_cache:
            c = Counter()
            for i in key:
                if i in cand_map:
                    c[int(cand_map[i]["team"])] += 1
            club_cache[key] = c
        return club_cache[key]

    best = None
    for g1, g2 in combinations(gks, 2):
        if g1["price"] + g2["price"] > BUDGET:
            continue
        gk_clubs = {int(g1["team"]): 1}
        gk_clubs[int(g2["team"])] = gk_clubs.get(int(g2["team"]), 0) + 1
        limits = {club: 3 - n - forced_by_club.get(club, 0) for club, n in gk_clubs.items()}
        out_budget = BUDGET - g1["price"] - g2["price"]
        for e in entries:
            if e["cost"] > out_budget:
                continue
            c = club_counts(e)
            if any(c.get(club, 0) > lim for club, lim in limits.items()):
                continue
            total = g1["proj"] + g2["proj"] + e["proj"]
            if best is None or total > best["total"]:
                best = {
                    "total": total,
                    "squad": [all_by_id[i] for i in e["path"]] + [g1, g2],
                }
    return best


def player_row(p):
    opp = f"vs {p['opponent_short']} ({'K' if p['is_home'] else 'T'}, FDR {p['fdr']})"
    mins = f"mnt {p['rel_minutes']} {p['rel_label']}" if p.get("rel_label") and p["rel_minutes"] < 2000 else ""
    return f"  {p['web_name']:<20s} {p['team_short']:<4s} {fmt_price(p['price']):<8s} proyeksi {p['proj']:>5.2f}  {opp}  {mins}"


def print_squad(squad, title, total_proj):
    print("\n" + "=" * 72)
    print(f"{title}")
    print("=" * 72)
    for pos in POS_ORDER:
        print(f"\n{pos} ({sum(1 for p in squad if p['pos'] == pos)}/{NEED[pos]}):")
        for p in sorted([p for p in squad if p["pos"] == pos], key=lambda p: p["proj"], reverse=True):
            print(player_row(p))
    total_cost = sum(p["price"] for p in squad)
    print("\n" + "-" * 72)
    print(f"Total nilai tim : {fmt_price(total_cost)}")
    print(f"Sisa budget     : {fmt_price(BUDGET - total_cost)}")
    print(f"Total proyeksi  : {total_proj:.2f} poin")


def print_xi(squad, total_proj):
    xi_ready = [
        {
            "id": p["id"],
            "web_name": p["web_name"],
            "team_short": p["team_short"],
            "team": int(p["team"]),
            "pos": p["pos"],
            "price": p["price"],
            "proj": p["proj"],
            "opponent_short": p.get("opponent_short"),
            "is_home": p.get("is_home"),
            "fdr": p.get("fdr"),
            "chance": p.get("chance"),
            "status": p.get("status"),
        }
        for p in squad
    ]
    result = best_xi(xi_ready)
    if not result:
        return
    print("\n" + "=" * 72)
    print(f"XI TERBAIK (Formasi {result['formation'][0]}-{result['formation'][1]}-{result['formation'][2]})")
    print("=" * 72)
    for pos in POS_ORDER:
        group = [p for p in result["xi"] if p["pos"] == pos]
        if not group:
            continue
        print(f"\n{pos}:")
        for p in sorted(group, key=lambda p: p["proj"], reverse=True):
            tag = ""
            if result["captain"] and p["id"] == result["captain"]["id"]:
                tag = "  <<< KAPTEN"
            elif result["vice"] and p["id"] == result["vice"]["id"]:
                tag = "  <<< WAKIL KAPTEN"
            opp = f"vs {p['opponent_short']} ({'K' if p['is_home'] else 'T'})" if p.get("opponent_short") else "bye"
            print(f"  {p['web_name']:<20s} {p['team_short']:<4s} proyeksi {p['proj']:>5.2f}  {opp}{tag}")
    print("\nCadangan:")
    for p in result["bench"]:
        print(f"  {p['web_name']} ({p['team_short']}) - proyeksi {p['proj']:.2f}")
    print(f"\nTotal proyeksi XI: {result['total']} poin")


def main():
    import sys

    horizon = 1
    if "--gws" in sys.argv:
        try:
            horizon = max(1, min(5, int(sys.argv[sys.argv.index("--gws") + 1])))
        except (ValueError, IndexError):
            horizon = 1

    clear_cache()
    gd = get_game_data(force=True)
    df = build_projection_table(gd)

    from fpl.paststats import load as load_past
    from fpl.reliability import adjust, load as load_rel

    rel = load_rel(gd)
    load_past(gd)
    df = adjust(df, rel)
    df = df.dropna(subset=["proj"])

    gw_projs = None
    if horizon > 1:
        from fpl.horizon import horizon_df, player_gw_projections

        hdf = horizon_df(gd, df, horizon)
        hdf = hdf.dropna(subset=["horizon"])
        hdf["proj"] = hdf["horizon"]
        gw_projs = player_gw_projections(df, gd, horizon)
        df = hdf

    by_name = {p["web_name"].lower(): p for p in df.to_dict("records")}

    haaland = by_name.get("haaland")
    saka = by_name.get("saka")
    tzolis = by_name.get("tzolis")

    scenarios = [("TIM OPTIMAL (tanpa paksaan)", [])]
    if haaland:
        scenarios.append(("ALTERNATIF: WAJIB HAALAND", [haaland]))
    if saka:
        scenarios.append(("ALTERNATIF: WAJIB SAKA", [saka]))
    if tzolis:
        scenarios.append(("ALTERNATIF: WAJIB TZOLIS (pilihan komunitas)", [tzolis]))

    print(f"REKOMENDASI TIM - GAMEWEEK {gd.next_event['id']}")
    print(f"Deadline: {gd.next_event.get('deadline_time')}")

    results = []
    for title, forced in scenarios:
        res = solve(gd, df, forced)
        if res:
            results.append((title, forced, res))

    for title, forced, res in results:
        errors = validate_squad(res["squad"])
        if errors:
            print(f"PERINGATAN skenario {title}: tidak valid - {', '.join(errors)}")
        print_squad(res["squad"], title, res["total"])
        print_xi(res["squad"], res["total"])
        print()

    if len(results) > 1:
        print("=" * 72)
        print("PERBANDINGAN SKENARIO")
        print("=" * 72)
        for title, forced, res in results:
            squad = res["squad"]
            names = [p["web_name"] for p in squad if p["id"] in [f["id"] for f in forced]]
            print(f"{title:<30s} proyeksi {res['total']:>6.2f}  nilai {fmt_price(sum(p['price'] for p in squad))}")

    winner_title, winner_forced, winner = results[0]

    if horizon > 1 and gw_projs:
        from fpl.horizon import squad_plan

        print("\n" + "=" * 72)
        print(f"RENCANA {horizon} GAMEWEEK (XI boleh dirotasi gratis - tanpa transfer)")
        print("=" * 72)
        xi_ready = [
            {
                "id": p["id"],
                "web_name": p["web_name"],
                "team_short": p["team_short"],
                "team": int(p["team"]),
                "pos": p["pos"],
                "price": p["price"],
                "proj": p["proj"],
                "photo_code": p.get("photo_code"),
            }
            for p in winner["squad"]
        ]
        plans = squad_plan(xi_ready, gw_projs, horizon)
        cur = gd.next_event["id"]
        for i, plan in enumerate(plans):
            gw = cur + i
            print(f"\nGW {gw}: total XI {plan['total']:.2f} poin (formasi {plan['formation'][0]}-{plan['formation'][1]}-{plan['formation'][2]})")
            cap = plan["captain"]["web_name"] if plan["captain"] else "-"
            vice = plan["vice"]["web_name"] if plan["vice"] else "-"
            print(f"  Kapten: {cap} | Wakil: {vice}")
            for pos in POS_ORDER:
                group = [p for p in plan["xi"] if p["pos"] == pos]
                if not group:
                    continue
                names = ", ".join(f"{p['web_name']} ({p['proj']:.2f})" for p in sorted(group, key=lambda p: p["proj"], reverse=True))
                print(f"  {pos}: {names}")
        tot = sum(p["total"] for p in plans)
        print(f"\nTotal {horizon} GW: {tot:.2f} poin proyeksi dengan 0 transfer.")
        print("Transfer hanya diperlukan jika pemain harus dikeluarkan dari 15 skuad - rotasi XI gratis.")
    print(f"\n>>> REKOMENDASI UTAMA: {winner_title} (total proyeksi {winner['total']:.2f} poin)")

    squad_file = DATA_DIR / "squad.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    squad_file.write_text(json.dumps([p["id"] for p in winner["squad"]]))
    print(f"Skuad rekomendasi tersimpan ke {squad_file} (Team Builder > Muat Tim Tersimpan)")


if __name__ == "__main__":
    main()
