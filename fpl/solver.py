POS_IDX = {"DEF": 0, "MID": 1, "FWD": 2}


def pareto_add(frontiers, key, entry):
    lst = list(frontiers.get(key, []))
    lst.append(entry)
    lst.sort(key=lambda e: (e["cost"], -e["proj"]))
    pruned = []
    best_proj = -1.0
    for e in lst:
        if e["proj"] > best_proj:
            pruned.append(e)
            best_proj = e["proj"]
    frontiers[key] = pruned


def dp_select(candidates, forced, budget):
    pd = sum(1 for f in forced if f["pos"] == "DEF")
    pm = sum(1 for f in forced if f["pos"] == "MID")
    pf = sum(1 for f in forced if f["pos"] == "FWD")
    start = {
        "cost": sum(f["price"] for f in forced),
        "proj": sum(f["proj"] for f in forced),
        "path": tuple(f["id"] for f in forced),
    }
    frontiers = {(pd, pm, pf): [start]}
    for p in candidates:
        pi = POS_IDX[p["pos"]]
        keys = list(frontiers.items())
        for (d, m, f), entries in keys:
            nd, nm, nf = d + (pi == 0), m + (pi == 1), f + (pi == 2)
            if nd > 5 or nm > 5 or nf > 3:
                continue
            nkey = (nd, nm, nf)
            for e in entries:
                ncost = e["cost"] + p["price"]
                if ncost > budget:
                    continue
                pareto_add(
                    frontiers,
                    nkey,
                    {"cost": ncost, "proj": e["proj"] + p["proj"], "path": e["path"] + (p["id"],)},
                )
    return frontiers.get((5, 5, 3), [])


def best_entry(entries, budget):
    best = None
    for e in entries:
        if e["cost"] > budget:
            break
        if best is None or e["proj"] > best["proj"]:
            best = e
    return best
