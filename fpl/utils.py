from datetime import datetime, timedelta, timezone

# Indonesian timezone (WIB = UTC+7)
WIB_TZ = timezone(timedelta(hours=7))
HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def fmt_deadline_wib(deadline_iso, format_type="full"):
    """Convert FPL ISO deadline string (UTC) to formatted Indonesian WIB string.

    Args:
        deadline_iso: ISO 8601 string from FPL API, e.g. "2026-08-30T10:00:00Z"
        format_type: "full" (Sabtu, 30 Agu 2026 · 17:00 WIB),
                     "short" (30 Agu · 17:00 WIB),
                     "date_only" (30 Agu 2026),
                     "time_only" (17:00 WIB)

    Returns: Formatted string in Indonesian WIB time
    """
    if not deadline_iso:
        return "-"
    try:
        dt = datetime.fromisoformat(deadline_iso.replace("Z", "+00:00"))
        wib = dt.astimezone(WIB_TZ)
        hari = HARI_ID[wib.weekday()]
        bulan = BULAN_ID[wib.month - 1]
        if format_type == "full":
            return f"{hari}, {wib.day} {bulan} {wib.year} pukul {wib.strftime('%H:%M')} WIB"
        elif format_type == "short":
            return f"{wib.day} {bulan} ({wib.strftime('%H:%M')} WIB)"
        elif format_type == "date_only":
            return f"{wib.day} {bulan} {wib.year}"
        elif format_type == "time_only":
            return f"{wib.strftime('%H:%M')} WIB"
        return f"{hari}, {wib.day} {bulan} ({wib.strftime('%H:%M')} WIB)"
    except Exception:
        return str(deadline_iso)[:16].replace("T", " ")


POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

STATUS_LABELS = {
    "a": "Tersedia",
    "d": "Diragukan",
    "i": "Cedera",
    "u": "Tidak Tersedia",
    "n": "Tidak Masuk Skuad",
}

FDR_LABELS = {1: "Sangat Mudah", 2: "Mudah", 3: "Sedang", 4: "Sulit", 5: "Sangat Sulit"}

FDR_COLORS = {1: "green", 2: "lightgreen", 3: "gray", 4: "orange", 5: "red"}

FDR_MULT = {1: 1.12, 2: 1.06, 3: 1.0, 4: 0.92, 5: 0.85}

# Clean sheet points per position (FPL rules)
CS_POINTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}

# Threat score normalization — typical top threat is ~1200 over a season (~32 per GW)
THREAT_NORM_FACTOR = 40.0

# Baseline xGI per 90 mins for normalization (top attackers ~0.8, average ~0.25)
XGI_PER90_BASELINE = 0.8

# ICT Index baseline for normalization (top performers ~8-10, average ~3-4)
ICT_BASELINE = 6.0

# Creativity per game normalization — typical top creators ~50-60/game
CREATIVITY_NORM_FACTOR = 50.0

# Bonus points per game baseline — top bonus earners ~1.5-2.0/game
BONUS_BASELINE = 1.5

POSITION_COLORS = {"GK": "yellow", "DEF": "blue", "MID": "green", "FWD": "red"}


def fmt_price(now_cost):
    return f"£{now_cost / 10:.1f}m"


def pos_badge(pos):
    color = POSITION_COLORS.get(pos, "gray")
    return f":{color}[{pos}]"


def fdr_badge(fdr):
    label = FDR_LABELS.get(fdr, "-")
    color = FDR_COLORS.get(fdr, "gray")
    return f":{color}[{label}]"


def home_away_badge(is_home):
    return ":blue[Kandang]" if is_home else ":orange[Tandang]"


def status_badge(status):
    label = STATUS_LABELS.get(status, status)
    color = "green" if status == "a" else "red"
    return f":{color}[{label}]"


def remaining_time(deadline_iso):
    if not deadline_iso:
        return "Tidak diketahui"
    deadline = datetime.fromisoformat(deadline_iso.replace("Z", "+00:00"))
    diff = deadline - datetime.now(timezone.utc)
    if diff.total_seconds() <= 0:
        return "Deadline sudah lewat"
    secs = int(diff.total_seconds())
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    return f"{days} hari {hours:02d} jam {mins:02d} menit"
