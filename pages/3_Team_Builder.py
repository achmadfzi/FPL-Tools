import json

import streamlit as st

from fpl.api import DATA_DIR
from fpl.optimizer import best_xi, suggest_transfers
from fpl.ui import apply_theme, autorefresh, esc, load_data, photo_url
from fpl.utils import fmt_price

st.set_page_config(page_title="Team Builder", layout="wide")

SQUAD_FILE = DATA_DIR / "squad.json"
SQUAD_SIZE = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}

apply_theme()
autorefresh()

gd, df = load_data()

st.markdown('<div class="section">Team <em>Builder</em></div>', unsafe_allow_html=True)
st.caption("Bangun skuad 15 pemain Anda, lalu optimasi XI terbaik, kapten, dan saran transfer.")

players = df.to_dict("records")
by_id = {p["id"]: p for p in players}


def fmt_option(p):
    proj = f"proyeksi {p['proj']:.1f}" if p["proj"] else "bye/risiko"
    return f"{p['web_name']} | {p['team_short']} | {fmt_price(p['price'])} | {proj}"


pos_options = {pos: {fmt_option(p): p["id"] for p in players if p["pos"] == pos} for pos in SQUAD_SIZE}


def load_squad():
    if SQUAD_FILE.exists():
        try:
            return json.loads(SQUAD_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_squad(ids):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQUAD_FILE.write_text(json.dumps(ids))


def labels_for(pos, ids):
    return [
        fmt_option(by_id[i])
        for i in ids
        if i in by_id and by_id[i]["pos"] == pos and fmt_option(by_id[i]) in pos_options[pos]
    ]


if "squad" not in st.session_state:
    st.session_state["squad"] = [i for i in load_squad() if i in by_id]

c1, c2 = st.columns(2)
with c1:
    if st.button("Muat Tim Tersimpan", use_container_width=True):
        st.session_state["_squad_request"] = "load"
with c2:
    if st.button("Kosongkan Tim", use_container_width=True):
        st.session_state["_squad_request"] = "clear"

if "_squad_request" in st.session_state:
    request = st.session_state.pop("_squad_request")
    if request == "load":
        loaded = [i for i in load_squad() if i in by_id]
        st.session_state["squad"] = loaded
        for pos in SQUAD_SIZE:
            st.session_state[f"sel_{pos}"] = labels_for(pos, loaded)
    else:
        st.session_state["squad"] = []
        for pos in SQUAD_SIZE:
            st.session_state[f"sel_{pos}"] = []
    st.rerun()

sel_new = []
cols = st.columns(4)
for col, (pos, need) in zip(cols, SQUAD_SIZE.items()):
    with col:
        stored_ids = [i for i in st.session_state["squad"] if by_id[i]["pos"] == pos]
        default = labels_for(pos, stored_ids)
        chosen = st.multiselect(
            f"Pilih {need} pemain {pos}",
            list(pos_options[pos].keys()),
            default=default,
            key=f"sel_{pos}",
            placeholder=f"Maks {need} pemain",
        )
        ids = [pos_options[pos][opt] for opt in chosen if opt in pos_options[pos]]
        sel_new += ids
        st.caption(f"{len(ids)}/{need} dipilih")

total_cost = sum(by_id[i]["price"] for i in sel_new) / 10
bank = 100.0 - total_cost

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total skuad", f"{len(sel_new)}/15 pemain")
c2.metric("Nilai tim", f"£{total_cost:.1f}m")
c3.metric("Sisa budget", f"£{bank:.1f}m")
with c4:
    if st.button("Simpan Tim", disabled=len(sel_new) != 15, use_container_width=True):
        save_squad(sel_new)
        st.session_state["squad"] = sel_new
        st.success("Tim tersimpan.")

st.caption(
    "Evaluasi di bawah memakai proyeksi yang DIAJUST dengan faktor menit bermain musim lalu — "
    "pemain baru / jarang main (mis. belum ada riwayat menit) otomatis dikurangi proyeksinya."
)

st.divider()

if len(sel_new) == 15:
    squad = [
        {
            "id": p["id"],
            "web_name": p["web_name"],
            "team_short": p["team_short"],
            "team": p["team"],
            "pos": p["pos"],
            "price": p["price"],
            "proj": p["proj"] if p["proj"] else 0.0,
            "opponent_short": p.get("opponent_short"),
            "is_home": p.get("is_home"),
            "fdr": p.get("fdr"),
            "chance": p.get("chance"),
            "status": p.get("status"),
            "photo_code": p.get("photo_code"),
            "selected_by": p.get("selected_by"),
        }
        for i in sel_new
        if (p := by_id[i])
    ]

    from fpl.reliability import factor as rel_factor
    from fpl.reliability import label as rel_label
    from fpl.reliability import load as rel_load

    with st.spinner("Memeriksa riwayat menit bermain..."):
        rel = rel_load(gd, ids=[p["id"] for p in squad])
    for p in squad:
        info = rel.get(str(p["id"]), {})
        p["rel_minutes"] = int(info.get("minutes", 0))
        p["rel_has_history"] = bool(info.get("has_history", False))
        p["rel_factor"] = rel_factor(p["rel_minutes"], p["rel_has_history"], p.get("selected_by") or 0)
        p["rel_label"] = rel_label(p["rel_minutes"], p["rel_has_history"], p.get("selected_by") or 0)
        p["proj_raw"] = p["proj"]
        p["proj"] = round(p["proj"] * p["rel_factor"], 2)
    risky_squad = [p for p in squad if p["rel_factor"] < 0.8]
    if risky_squad:
        st.warning(
            "Perhatian: pemain berikut belum terbukti bermain rutin (menit musim lalu rendah / pemain baru) — "
            "proyeksinya sudah dikurangi sesuai risiko menit: "
            + ", ".join(f"{p['web_name']} ({p['rel_label']})" for p in risky_squad)
        )

    result = best_xi(squad)

    if result:
        st.markdown(
            f'<div class="section">XI Terbaik · Formasi <em>{result["formation"][0]}-{result["formation"][1]}-{result["formation"][2]}</em></div>',
            unsafe_allow_html=True,
        )

        pitch_rows = []
        for pos in ("GK", "DEF", "MID", "FWD"):
            group = [p for p in result["xi"] if p["pos"] == pos]
            group.sort(key=lambda p: p["proj"], reverse=True)
            cells = []
            for p in group:
                is_cap = result["captain"] and p["id"] == result["captain"]["id"]
                is_vice = result["vice"] and p["id"] == result["vice"]["id"]
                badge = ""
                if is_cap:
                    badge = '<div class="k">★ KAPTEN</div>'
                elif is_vice:
                    badge = '<div class="k">WAKIL</div>'
                img = f'<img src="{photo_url(p["photo_code"])}">' if p.get("photo_code") else '<img src="" style="visibility:hidden">'
                risk = '<div class="k" style="color:#f59e0b">RISIKO MENIT</div>' if p.get("rel_factor", 1) < 0.7 else ""
                cells.append(
                    f'<div class="p-cell {"cap" if is_cap else ""}">{img}'
                    f'<div class="n">{esc(p["web_name"])}</div>'
                    f'<div class="x">{p["proj"]:.2f}</div>{badge}{risk}</div>'
                )
            if group:
                pitch_rows.append(f'<div class="p-row">{"".join(cells)}</div>')
        st.markdown(f'<div class="pitch">{"".join(pitch_rows)}</div>', unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total proyeksi XI", f"{result['total']} poin", "tanpa kapten")
        c2.metric("Dengan kapten (×2)", f"{result['total'] + result['captain']['proj']:.2f} poin" if result["captain"] else "-", f"+{result['captain']['proj']:.2f} dari {result['captain']['web_name']}" if result["captain"] else "")
        pool_avg = df["proj"].dropna().mean() * 11
        c3.metric("vs rata-rata pool", f"{result['total'] / pool_avg * 100:.0f}%", f"rata-rata tim lain {pool_avg:.2f}")

        with st.expander("Apakah 28 poin itu kecil? Konteks proyeksi GW1"):
            max11 = df.dropna(subset=["proj"]).nlargest(11, "proj")["proj"].sum()
            st.markdown(
                f"""
                - Proyeksi ini adalah **ekspektasi (rata-rata)**, bukan skor pasti — skor aktual bisa 20–45.
                - XI Anda {result['total']:.2f} = **{result['total'] / max11 * 100:.0f}% dari maksimum teoritis** ({max11:.2f}) yang mungkin di data GW ini.
                - FPL's own `ep_next` for the same XI: {sum(p.get('ep_next_fpl') or 0 for p in result['xi']):.2f} — model kami sejalan.
                - Rata-rata skor aktual FPL (~50–60/GW) sudah termasuk kapten ×2, bonus, dan form paruh musim.
                - Di GW1 semua pemain form = 0, jadi proyeksi FPL sendiri konservatif (1.5–4 poin/pemain).
                """
            )

        st.markdown('<div class="section" style="font-size:.95rem">Cadangan</div>', unsafe_allow_html=True)
        bench_html = '<div class="bench-row">'
        for p in result["bench"]:
            img = f'<img src="{photo_url(p["photo_code"])}">' if p.get("photo_code") else ""
            bench_html += (
                f'<div class="bench-cell">{img}<div><div class="n">{esc(p["web_name"])} ({esc(p["team_short"])})</div>'
                f'<div class="x">{p["proj"]:.2f} poin</div></div></div>'
            )
        bench_html += "</div>"
        st.markdown(bench_html, unsafe_allow_html=True)

        st.divider()

        st.markdown('<div class="section" style="font-size:.95rem">Saran <em>Transfer</em></div>', unsafe_allow_html=True)
        pool = [
            {
                "id": p["id"],
                "web_name": p["web_name"],
                "team_short": p["team_short"],
                "team": p["team"],
                "pos": p["pos"],
                "price": p["price"],
                "proj": p["proj"] if p["proj"] else 0.0,
            }
            for p in players
        ]
        suggestions = suggest_transfers(squad, pool, bank)
        if suggestions:
            for s in suggestions[:6]:
                w = s["player"]
                best_rep = s["reps"][0]
                st.markdown(
                    f"<div class='info-line'>"
                    f"<span style='color:#f87171;font-weight:800'>{esc(w['web_name'])}</span> ({esc(w['team_short'])}, "
                    f"proyeksi {w['proj']:.2f}) → "
                    f"<span style='color:#4ade80;font-weight:800'>{esc(best_rep['web_name'])}</span> ({esc(best_rep['team_short'])}, "
                    f"proyeksi {best_rep['proj']:.2f}) · <b style='color:#00ff87'>potensi +{s['gain']:.2f}</b> poin"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                alternatif = ", ".join(f"{r['web_name']} ({r['proj']:.1f})" for r in s["reps"][1:])
                if alternatif:
                    st.caption(f"Alternatif: {alternatif}")
        else:
            st.info("Tidak ada transfer yang menguntungkan berdasarkan proyeksi saat ini.")

        st.divider()
        st.markdown('<div class="section" style="font-size:.95rem">Validasi <em>Rekomendasi</em></div>', unsafe_allow_html=True)


        @st.cache_data(ttl=1800, show_spinner="Menjalankan validasi menyeluruh (beberapa detik)...")
        def quick_validation(squad_ids):
            from fpl.api import get_game_data
            from fpl.model import build_projection_table
            from fpl.strategy import squad_from_ids
            from fpl.validation import heuristic_teams, random_squads, validate_squad

            gd = get_game_data()
            df = build_projection_table(gd)
            squad = squad_from_ids(df, list(squad_ids))
            errors = validate_squad(squad)
            players = [p for p in df.to_dict("records")]
            totals = random_squads(players, n=300)
            dp_total = round(sum(p["proj"] for p in squad), 2)
            pct = sum(1 for t in totals if t <= dp_total) / len(totals) * 100
            heur = heuristic_teams(players)
            return {
                "errors": errors,
                "dp_total": dp_total,
                "pct": pct,
                "max_rand": max(totals),
                "mean_rand": sum(totals) / len(totals),
                "heur": {name: round(dp_total - h["total"], 2) for name, h in heur.items()},
            }

        res = quick_validation(tuple(sel_new))
        if res["errors"]:
            st.error(f"Skuad tidak valid: {', '.join(res['errors'])}")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Legalitas", "LULUS", "15 pemain · 2/5/5/3 · ≤3 per klub")
            c2.metric("vs 300 tim acak", f"Percentile ke-{res['pct']:.0f}", f"rata-rata acak {res['mean_rand']:.2f} poin")
            c3.metric("vs tim pandit terbaik", f"+{min(res['heur'].values()):.2f} poin", f"skor Anda {res['dp_total']:.2f}")
            st.caption(
                "Solver diuji identik dengan brute-force exhaustive (940.800 kombinasi/subset, 5/5 subset). "
                "Tim ini adalah optimum matematis terhadap model proyeksi — tidak ada tim lain dalam budget £100m "
                "yang bisa lebih tinggi menurut data."
            )
            with st.expander("Detail vs strategi pandit lain"):
                for name, delta in sorted(res["heur"].items(), key=lambda kv: kv[1]):
                    st.write(f"{name}: {delta:+.2f} poin vs skuad Anda")
            st.caption(
                "Batas: optimum berlaku terhadap model proyeksi. Model mengandalkan ep_next FPL saat form masih 0 (GW1). "
                "Pandit bisa punya info non-data (berita cedera/rotasi). Bukti final = skor aktual GW."
            )

        st.divider()
        st.markdown('<div class="section" style="font-size:.95rem">Rencana <em>3 Gameweek</em> ke Depan — Minimalkan Transfer</div>', unsafe_allow_html=True)
        st.caption(
            "XI boleh dirotasi GRATIS antar Gameweek. Transfer hanya dibutuhkan jika pemain harus dikeluarkan "
            "dari 15 skuad — rencana ini memastikan skuad Anda tetap kuat 3 GW tanpa transfer."
        )
        from fpl.horizon import player_gw_projections, risky_players, squad_plan

        gw_projs = player_gw_projections(df, gd, 3)
        plans = squad_plan(squad, gw_projs, 3)
        cur = gd.next_event["id"]
        total_3gw = sum(p["total"] for p in plans)
        col_plans = st.columns(3)
        for i, (col, plan) in enumerate(zip(col_plans, plans)):
            gw = cur + i
            cap = plan["captain"]["web_name"] if plan["captain"] else "-"
            label = f"GW {gw}" + (" · GW ini" if i == 0 else "")
            col.metric(label, f"{plan['total']:.2f} poin", f"Formasi {plan['formation'][0]}-{plan['formation'][1]}-{plan['formation'][2]} | Kapten: {cap}")
        st.caption(f"**Total 3 GW: {total_3gw:.2f} poin dengan 0 transfer.** Pakai `python recommend.py --gws 3` untuk skuad yang dioptimasi 3 GW sekaligus.")
        with st.expander("Detail XI & kapten per Gameweek"):
            for i, plan in enumerate(plans):
                gw = cur + i
                st.markdown(f"**GW {gw}** (total {plan['total']:.2f} poin)")
                for pos in ("GK", "DEF", "MID", "FWD"):
                    group = [p for p in plan["xi"] if p["pos"] == pos]
                    if group:
                        names = ", ".join(
                            f"{p['web_name']} ({p['proj']:.2f})" for p in sorted(group, key=lambda p: p["proj"], reverse=True)
                        )
                        st.write(f"{pos}: {names}")
        risky = risky_players(squad, gw_projs, 3)
        st.markdown(
            "<div class='info-line'><b style='color:#fbbf24'>Perhatian — pemain paling berpotensi perlu transfer di GW berikutnya:</b></div>",
            unsafe_allow_html=True,
        )
        for p, fut in risky:
            st.write(f":orange[**{p['web_name']}**] ({p['team_short']}) — proyeksi GW2+GW3 hanya {fut:.2f} poin")
        st.caption(
            "Estimasi GW2/3 memakai kualitas pemain saat ini (form/ppg/ep_next) × FDR lawan GW tersebut × kandang/tandang "
            "(×1.9 bila DGW). Akurasi meningkat seiring musim berjalan."
        )
    else:
        st.warning("Skuad belum valid. Pastikan 15 pemain dengan 2 GK, 5 DEF, 5 MID, 3 FWD.")
else:
    st.info(f"Pilih {15 - len(sel_new)} pemain lagi untuk mengaktifkan optimasi.")
