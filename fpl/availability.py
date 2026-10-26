"""Player availability: injury/suspension news and chance of playing.

This is the single source of truth for interpreting FPL's availability
fields. The same helpers are used by the projection model, the Monte Carlo
simulator, the transfer planner and the UI so a player can never be
"available" in one place and "injured" in another.

FPL fields (bootstrap-static):
- ``status``: a=available, d=doubtful, i=injured, s=suspended,
  u=unavailable, n=not in squad.
- ``news``: free-text update, e.g. ``Hamstring injury - Expected back 21 Nov``
  or ``Has joined Al Hilal permanently``.
- ``chance_of_playing_this_round`` / ``chance_of_playing_next_round``:
  0/25/50/75/100 percent (null means no doubt for a fit player).

``chance_of_playing_*`` is the probability of playing, NOT ownership. The
latter is ``selected_by_percent`` and is only used as context.
"""

import math
import re

from .utils import STATUS_LABELS

UNAVAILABLE_STATUSES = ("i", "u", "n", "s")


def _clean_text(value):
    """Return a stripped string, treating None/NaN/"nan" as empty."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none") else text


def normalize_status(status):
    """Normalise an FPL status code; unknown/empty becomes 'a'."""
    code = _clean_text(status).lower()
    return code if code in STATUS_LABELS else ("a" if not code else code)


def chance_pct(value):
    """Convert FPL chance-of-playing to 0-100 percent.

    Accepts None/NaN, integer percent (0/25/50/75/100) and fractions
    (0.0-1.0) used by some internal helpers.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "")
        if not value:
            return None
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(pct):
        return None
    if 0 < pct <= 1.0:
        pct *= 100.0
    return max(0.0, min(100.0, pct))


def raw_chance(player, which="next"):
    """Raw official chance (0-100) for 'this' or 'next' round, or None."""
    if player is None:
        return None
    if which == "this":
        keys = ("chance_this", "chance_of_playing_this_round")
    else:
        keys = ("chance_next", "chance_of_playing_next_round", "chance")
    for key in keys:
        if key in player:
            return chance_pct(player.get(key))
    return None


def chance_factor(player, which="next"):
    """Probability of playing as a 0.0-1.0 factor.

    Rules:
    - injured/unavailable/suspended/not-in-squad -> 0
    - doubtful without an official percentage -> 75%
    - available without an official percentage -> 100%
    """
    status = normalize_status(player.get("status") if player is not None else None)
    if status in UNAVAILABLE_STATUSES:
        return 0.0
    pct = raw_chance(player, which)
    if pct is None:
        return 0.75 if status == "d" else 1.0
    return max(0.0, min(1.0, pct / 100.0))


def parse_news(news):
    """Classify FPL news text and extract a return date when present.

    Returns ``{"category", "return_text", "news"}``. Categories:
    injury, illness, suspension, unavailable (transfer/loan/not in squad),
    doubt, fit, other.
    """
    text = _clean_text(news)
    lower = text.lower()
    if not lower:
        return {"category": "fit", "return_text": "", "news": ""}

    if "suspended" in lower or "suspension" in lower:
        category = "suspension"
    elif "illness" in lower or "sick" in lower or "virus" in lower:
        category = "illness"
    elif "injury" in lower or "knock" in lower:
        category = "injury"
    elif any(
        phrase in lower
        for phrase in (
            "has joined",
            "joined ",
            "departed",
            "on loan",
            "loan until",
            "not included in squad",
            "returned to",
            "free agent",
        )
    ):
        category = "unavailable"
    elif "doubt" in lower:
        category = "doubt"
    else:
        category = "other"

    return_text = ""
    match = re.search(r"expected back\s+([^.;]+)", text, re.IGNORECASE)
    if match:
        return_text = match.group(1).strip()
    if not return_text:
        match = re.search(r"suspended until\s+([^.;]+)", text, re.IGNORECASE)
        if match:
            return_text = match.group(1).strip()
    if not return_text and "unknown return date" in lower:
        return_text = "Tidak diketahui"

    return {"category": category, "return_text": return_text, "news": text}


def _display_pct(player, which):
    """Chance shown in the UI: unavailable is always 0%, fit defaults 100%."""
    status = normalize_status(player.get("status") if player is not None else None)
    if status in UNAVAILABLE_STATUSES:
        return 0.0
    pct = raw_chance(player, which)
    if pct is None:
        return 75.0 if status == "d" else 100.0
    return pct


_CATEGORY_LABELS = {
    "injury": "Cedera",
    "illness": "Sakit",
    "suspension": "Suspended",
    "unavailable": "Tidak tersedia",
    "doubt": "Diragukan",
    "fit": "Tersedia",
    "other": "Catatan",
}


def availability(player, which="next"):
    """Full availability view used by projections, transfers and the UI.

    Returns a dict with ``status``, ``status_label``, ``this_pct``,
    ``next_pct``, ``pct`` (next round), ``label``, ``category``, ``news``,
    ``return_text``, ``action``, ``severity`` and ``is_out``.
    """
    if player is None:
        player = {}
    status = normalize_status(player.get("status"))
    parsed = parse_news(player.get("news"))

    category = parsed["category"]
    if status == "i" and category in ("fit", "other"):
        category = "injury"
    elif status == "s":
        category = "suspension"
    elif status in ("u", "n") and category in ("fit", "other", "doubt"):
        category = "unavailable"
    elif status == "d" and category == "fit":
        category = "doubt"

    this_pct = _display_pct(player, "this")
    next_pct = _display_pct(player, "next")
    pct = next_pct if which == "next" else this_pct

    if pct <= 0:
        action = "JUAL SEKARANG"
        severity = 3
    elif pct < 75:
        action = "PANTAU"
        severity = 2
    elif pct < 100 or status == "d":
        action = "PANTAU"
        severity = 1
    else:
        action = "TAHAN"
        severity = 0

    if status == "d":
        label = f"Diragukan · {pct:.0f}%"
    elif status in ("i", "s", "u", "n"):
        label = f"{STATUS_LABELS.get(status, status)} · {pct:.0f}%"
    elif pct <= 0:
        label = "Tidak tersedia · 0%"
    else:
        label = _CATEGORY_LABELS.get(category, category)
        if pct < 100:
            label = f"{label} · {pct:.0f}%"

    return {
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "this_pct": round(this_pct, 1),
        "next_pct": round(next_pct, 1),
        "pct": round(pct, 1),
        "label": label,
        "category": category,
        "news": parsed["news"],
        "return_text": parsed["return_text"],
        "action": action,
        "severity": severity,
        "is_out": pct <= 0 or status in UNAVAILABLE_STATUSES,
    }


def is_available(player, min_chance=0):
    """True when the player can be bought under a minimum chance threshold."""
    av = availability(player)
    return not av["is_out"] and av["pct"] >= float(min_chance or 0)


def availability_gain(in_player, out_player):
    """Difference in next-round playing chance (percentage points)."""
    return round(availability(in_player)["pct"] - availability(out_player)["pct"], 1)
