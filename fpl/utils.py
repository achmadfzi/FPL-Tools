from datetime import datetime, timezone

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
