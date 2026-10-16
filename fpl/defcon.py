"""DefCon (defensive contribution) probability model — FPL 2026/27 rules.

Rules (from the official scoring):
- Defender: 10+ combined clearances, blocks, interceptions and tackles (CBIT)
  in a match -> 2 FPL points.
- Midfielder / Forward: 12+ CBIT plus ball recoveries (CBIRT) -> 2 points.
- Goalkeepers are NOT eligible.
- Points are capped at 2 per match, so a per-match hit probability is all we
  need to price the signal.

Estimation model (Gamma-Poisson / negative binomial mixture):
- Per-match qualifying-action counts come from the cached per-GW history
  (`player_history`, element-summary) — the API reports the exact counted
  value in `defensive_contribution` per match.
- When no history is cached yet we fall back to the bootstrap's
  `defensive_contribution_per_90` season rate with a weak prior.
- For a match with expected minutes m we compute
  X ~ NegativeBinomial(r=a, p=b/(b + m/90))  and  p_hit = P(X >= threshold).

This module is READ-ONLY with respect to the network: it only uses the local
history cache plus the bootstrap. Call `player_history.backfill()` to refresh
the underlying per-GW rows.
"""

import json
import time

from .api import DATA_DIR
from .utils import DC_THRESHOLD

FILE = DATA_DIR / "defcon.json"
TTL = 6 * 3600

# Prior strength in "pseudo defensive actions" (roughly one match of a busy
# centre-back) so a single big game does not inflate the estimate.
PRIOR_ACTIONS = 8.0

# Fallback per-90 prior rates by position (league averages, blended with the
# live bootstrap median when available).
PRIOR_PER90 = {"DEF": 8.0, "MID": 5.5, "FWD": 3.0, "GK": 0.0}


def _load_file():
    if FILE.exists():
        try:
            return json.loads(FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_file(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data))


def _bootstrap_priors(gd):
    """Positional median dc/90 from the live bootstrap, blended with constants."""
    by_pos = {"DEF": [], "MID": [], "FWD": []}
    for p in gd.players:
        pos = p.get("pos")
        if pos in by_pos and (p.get("minutes") or 0) >= 270:
            rate = float(p.get("dc_per90") or 0)
            if rate > 0:
                by_pos[pos].append(rate)
    priors = {}
    for pos, vals in by_pos.items():
        if vals:
            vals.sort()
            median = vals[len(vals) // 2]
            priors[pos] = max(0.5, 0.5 * median + 0.5 * PRIOR_PER90[pos])
        else:
            priors[pos] = PRIOR_PER90[pos]
    priors["GK"] = 0.0
    return priors


def _shrunk_rate(p, prior):
    """Bootstrap season rate shrunk toward the positional prior.

    Raw per-90 rates are extremely noisy for tiny samples (a 5-minute cameo
    can imply a 70+/90 rate), so we shrink by minutes played: full trust at
    ~5 matches (450 minutes).
    """
    minutes = float(p.get("minutes") or 0)
    dc_total = float(p.get("dc_total") or 0)
    if minutes <= 0:
        return prior
    obs = dc_total / (minutes / 90.0)
    w = min(1.0, minutes / 450.0)
    return max(0.3, w * obs + (1.0 - w) * prior)


def _nb_params(pos, rows, boot_rate, prior_rate):
    """Posterior (a, b) of the Gamma-Poisson model for one player.

    Returns (a, b, n_matches, method). `b` is a rate parameter such that
    X ~ NB(r=a, p=b/(b + minutes/90)) models a match with that many minutes.
    """
    k0 = PRIOR_ACTIONS
    if pos == "GK":
        return 0.0, 1.0, 0, "gk"

    played = [r for r in rows if (r.get("minutes") or 0) > 0][-8:]
    n = len(played)
    total_actions = sum(float(r.get("dc") or 0) for r in played)
    total_90s = sum((r.get("minutes") or 0) / 90.0 for r in played)

    if n >= 2 and total_90s > 0:
        lam = prior_rate
        a = k0 + total_actions
        b = k0 / lam + total_90s
        return a, b, n, "history"

    # Fallback: bootstrap season rate (weak prior anchored at the rate itself).
    rate = boot_rate if boot_rate and boot_rate > 0 else prior_rate
    rate = max(rate, 0.4)
    a = k0
    b = k0 / rate
    return a, b, 0, "bootstrap"


def hit_probability(pos, a, b, minutes):
    """P(reaching the DefCon threshold) for a match with `minutes` played."""
    if pos == "GK" or a <= 0 or minutes <= 0:
        return 0.0
    try:
        from scipy.stats import nbinom

        m90 = max(float(minutes), 0.0) / 90.0
        if m90 <= 0:
            return 0.0
        p = b / (b + m90)
        threshold = DC_THRESHOLD.get(pos, 999)
        cdf = float(nbinom.cdf(threshold - 1, a, p))
        return max(0.0, min(0.90, 1.0 - cdf))
    except Exception:
        # Poisson fallback (no scipy): use posterior mean rate.
        import math

        lam = (a / b) * (max(float(minutes), 0.0) / 90.0)
        threshold = DC_THRESHOLD.get(pos, 999)
        cdf = 0.0
        term = math.exp(-lam)
        for k in range(int(threshold)):
            cdf += term
            term *= lam / (k + 1)
        return max(0.0, min(0.90, 1.0 - cdf))


def build(gd, force=False):
    """Build/refresh DefCon parameters for every player (file-cache based).

    Returns dict {player_id: params}; params keys: a, b, n, method, lam90,
    pos, boot_rate, ts (all JSON-safe).
    """
    from . import player_history

    if FILE.exists() and not force:
        try:
            cached = _load_file()
            if cached.get("_meta", {}).get("ts", 0) > time.time() - TTL:
                return cached
        except Exception:
            pass

    priors = _bootstrap_priors(gd)
    hist_file = player_history._load_file()
    now = time.time()

    out = {"_meta": {"ts": now, "priors": priors}}
    for p in gd.players:
        pid = int(p["id"])
        pos = p.get("pos", "MID")
        prior = priors.get(pos, PRIOR_PER90.get(pos, 0.0))
        boot_rate = _shrunk_rate(p, prior)
        rows = []
        entry = hist_file.get(str(pid))
        if entry and isinstance(entry.get("rows"), list) and (now - entry.get("ts", 0)) < player_history.TTL:
            rows = entry["rows"]
        a, b, n, method = _nb_params(pos, rows, boot_rate, prior)
        lam90 = round(a / b, 3) if b > 0 and method != "gk" else 0.0
        out[str(pid)] = {
            "pos": pos,
            "a": round(a, 3),
            "b": round(b, 3),
            "n": n,
            "method": method,
            "lam90": lam90,
            "boot_rate": round(boot_rate, 3),
        }
    _save_file(out)
    return out


def load(gd, force=False):
    """Load DefCon parameters for the current squad/pool (cached 6h)."""
    return build(gd, force=force)


def prob_for(dc, pid, pos, minutes):
    """Convenience helper: probability for one player id from the built dict."""
    params = dc.get(str(int(pid))) if dc else None
    if not params:
        return 0.0
    return hit_probability(params.get("pos", pos), params.get("a", 0.0), params.get("b", 1.0), minutes)


def attach(df, dc):
    """Attach DefCon columns to a projection table (file-cache only).

    Adds: dc_prob (next match), dc_exp_pts (2 x prob), dc_lam90, dc_n, dc_method.
    Expected minutes are taken from `exp_minutes` when present, else a
    season-minutes proxy.
    """
    out = df.copy()

    def _minutes(row):
        em = row.get("exp_minutes")
        try:
            if em and float(em) > 0:
                return float(em)
        except (TypeError, ValueError):
            pass
        starts = int(row.get("starts") or 0)
        minutes = float(row.get("minutes") or 0)
        if starts > 0:
            return min(90.0, minutes / max(starts, 1))
        if minutes > 0:
            return 30.0
        return 0.0

    probs, lams, ns, methods = [], [], [], []
    for _, row in out.iterrows():
        params = dc.get(str(int(row["id"]))) if dc else None
        if not params:
            probs.append(0.0)
            lams.append(0.0)
            ns.append(0)
            methods.append("none")
            continue
        probs.append(hit_probability(params["pos"], params["a"], params["b"], _minutes(row)))
        lams.append(params.get("lam90", 0.0))
        ns.append(params.get("n", 0))
        methods.append(params.get("method", "none"))

    out["dc_prob"] = probs
    out["dc_exp_pts"] = [round(2.0 * p, 2) for p in probs]
    out["dc_lam90"] = lams
    out["dc_n"] = ns
    out["dc_method"] = methods
    return out


def label(prob):
    """Human label for UI display."""
    if prob is None:
        return "-"
    if prob >= 0.55:
        return "Elite DefCon"
    if prob >= 0.40:
        return "Sering DefCon"
    if prob >= 0.25:
        return "Kadang DefCon"
    if prob >= 0.10:
        return "Jarang DefCon"
    return "Minim DefCon"
