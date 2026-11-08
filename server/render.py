#!/usr/bin/env python3
"""
Render a 24-hour precipitation chart as a Kindle-ready PNG.

Runs on the server (cron, every 10 min). For each location it fetches the Met
Office UKV/Global blend from Open-Meteo, draws an 800x600 landscape chart,
rotates it to the Kindle Touch's native 600x800 portrait framebuffer and writes
an 8-bit greyscale PNG called rain-<slug>.png.

It also writes kindle.png: the chart for the Kindle's location, plus the
Kindle's battery level, read from the last heartbeat in the nginx log.

    python3 render.py /var/www/raindash
    python3 render.py . --demo               # synthetic data, no network

Only dependency: Pillow (sudo apt install python3-pil fonts-dejavu-core)
"""
import argparse
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# ---- config -----------------------------------------------------------------
# Defaults. Override in locations.json next to this script (kept out of git,
# so precise coordinates never end up in a public repo). See locations.example.json
LOCATIONS = {                    # slug: (display name, lat, lon)
    "lincoln": ("Lincoln", 53.23, -0.54),
    "basingstoke": ("Basingstoke", 51.27, -1.09),
}
KINDLE = "basingstoke"           # which location kindle.png shows

HEARTBEAT = "/var/log/raindash/heartbeat.log"   # written by nginx on each Kindle fetch
LOW_BATTERY = 20                 # % - below this (and not charging) show a warning
TZ = "Europe/London"
MODEL = "ukmo_seamless"          # UKV 2 km over the UK, Global 10 km beyond
ROTATE = 90                      # 90 or 270 depending on which way the Kindle sits
                                 # (0 = leave portrait, for testing on a PC)
W, H = 800, 600                  # landscape canvas, before rotation
SS = 2                           # supersample factor for smooth edges

# Y axis: square-root scale so drizzle is visible but a downpour fills the chart.
Y_MAX = 8.0                      # mm/h - anything above is clipped to the top
Y_TICKS = [(0.5, "0.5"), (1, "1"), (2, "2"), (4, "4"), (8, "8")]
LIGHT, HEAVY = 0.5, 4.0          # Met Office light / heavy rain thresholds, mm/h
WET = 0.1                        # mm/h considered "raining" for the headline

FONT_DIR = "/usr/share/fonts/truetype/dejavu"


# ---- data -------------------------------------------------------------------
def fetch(now, lat, lon):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&hourly=precipitation"
        f"&models={MODEL}&timezone={TZ.replace('/', '%2F')}&forecast_days=3"
    )
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)["hourly"]
    tz = ZoneInfo(TZ)
    pts = []
    for t, mm in zip(data["time"], data["precipitation"]):
        # Open-Meteo hourly precip is the total for the PRECEDING hour, so
        # centre each value on the middle of the hour it describes.
        ts = datetime.fromisoformat(t).replace(tzinfo=tz) - timedelta(minutes=30)
        pts.append((ts, mm or 0.0))
    return window(pts, now)


def demo(now):
    """A dry spell, a band of heavy rain, then showers - for testing the look."""
    start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    pts = []
    for i in range(28):
        h = i - 1
        mm = 3.6 * math.exp(-((h - 7) / 2.2) ** 2) + 0.9 * math.exp(-((h - 15) / 1.2) ** 2)
        mm += 0.35 * math.exp(-((h - 20) / 0.9) ** 2)
        pts.append((start + timedelta(hours=i, minutes=30), round(mm, 2)))
    return window(pts, now)


def window(pts, now):
    end = now + timedelta(hours=24)
    # keep one point either side of the window so the curve runs edge to edge
    keep = [p for p in pts if now - timedelta(hours=1) <= p[0] <= end + timedelta(hours=1)]
    if len(keep) < 6:
        raise SystemExit("Not enough forecast data returned")
    return keep, now, end


def load_config():
    global KINDLE
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locations.json")
    if os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
        LOCATIONS.clear()
        LOCATIONS.update({k: tuple(v) for k, v in cfg["locations"].items()})
        KINDLE = cfg.get("kindle", KINDLE)


def battery(now, path):
    """Battery % and charging flag from the newest heartbeat, or None if stale/missing."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2048))
            line = f.read().decode(errors="ignore").strip().splitlines()[-1]
        f = dict(p.split("=", 1) for p in line.split() if "=" in p)
        seen = datetime.fromisoformat(line.split()[0])
        if now - seen > timedelta(hours=1) or not f.get("bat", "").isdigit():
            return None
        return int(f["bat"]), f.get("chg") == "1"
    except (OSError, IndexError, ValueError):
        return None


# ---- curve smoothing (monotone cubic: no overshoot below zero) ---------------
def monotone(xs, ys, steps=8):
    n = len(xs)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
        else:
            a, b = m[i] / d[i], m[i + 1] / d[i]
            s = a * a + b * b
            if s > 9:
                t = 3 / math.sqrt(s)
                m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    out = []
    for i in range(n - 1):
        h = xs[i + 1] - xs[i]
        for k in range(steps):
            t = k / steps
            h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
            h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
            out.append((xs[i] + t * h, h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]))
    out.append((xs[-1], ys[-1]))
    return out


# ---- headline ---------------------------------------------------------------
def headline(pts, now, end):
    hourly = [(t, mm) for t, mm in pts if now - timedelta(minutes=30) <= t <= end]
    wet = [mm >= WET for _, mm in hourly]
    if not any(wet):
        return "Dry for the next 24 hours"
    peak = max(mm for _, mm in hourly)
    kind = "Heavy rain" if peak >= HEAVY else "Rain" if peak >= LIGHT else "Light rain"
    if wet[0]:
        for (t, _), w in zip(hourly, wet):
            if not w:
                return f"Raining now, dry by {(t - timedelta(minutes=30)).strftime('%H:%M')}"
        return "Raining for the next 24 hours"
    first = next(t for (t, _), w in zip(hourly, wet) if w)
    return f"{kind} from {(first - timedelta(minutes=30)).strftime('%H:%M')}"


# ---- drawing ----------------------------------------------------------------
def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size * SS)
    except OSError:
        return ImageFont.load_default(size * SS)


def render(pts, now, end, out, place, bat=None):
    img = Image.new("L", (W * SS, H * SS), 255)
    g = ImageDraw.Draw(img)
    S = lambda v: int(round(v * SS))

    # plot area
    L, R, T, B = 64, W - 24, 112, H - 56
    span = (end - now).total_seconds()
    xpx = lambda t: L + (R - L) * (t - now).total_seconds() / span
    ypx = lambda mm: B - (B - T) * math.sqrt(min(max(mm, 0), Y_MAX) / Y_MAX)

    # header
    g.text((S(L - 40), S(20)), headline(pts, now, end), font=font(34, True), fill=0)
    status = f"updated {now:%H:%M}"
    if bat:
        status += f"  ·  battery {bat[0]}%" + (" (charging)" if bat[1] else "")
    g.text((S(R), S(66)), status, font=font(18), fill=85, anchor="ra")
    if bat and bat[0] < LOW_BATTERY and not bat[1]:
        # low battery: swap the subtitle for a black banner that's hard to miss
        msg = f"Low battery {bat[0]}% - please plug me in"
        box = g.textbbox((S(L - 40), S(66)), msg, font=font(18, True))
        g.rectangle((box[0] - S(8), box[1] - S(5), box[2] + S(8), box[3] + S(5)), fill=0)
        g.text((S(L - 40), S(66)), msg, font=font(18, True), fill=255)
    else:
        g.text((S(L - 40), S(66)), f"{place}  ·  rain, mm per hour", font=font(18), fill=85)

    # gridlines + y labels
    for mm, label in Y_TICKS:
        y = ypx(mm)
        g.line([(S(L), S(y)), (S(R), S(y))], fill=204, width=S(1))
        g.text((S(L - 10), S(y)), label, font=font(16), fill=85, anchor="rm")
    for mm, word in ((LIGHT, "light"), (HEAVY, "heavy")):
        g.text((S(R - 4), S(ypx(mm) - 4)), word, font=font(14), fill=136, anchor="rb")

    # area: smoothed curve, clipped to the plot window
    xs = [(t - now).total_seconds() for t, _ in pts]
    ys = [mm for _, mm in pts]
    curve = [(L + (R - L) * x / span, ypx(y)) for x, y in monotone(xs, ys)]
    curve = [(min(max(x, L), R), y) for x, y in curve]
    poly = [(curve[0][0], B)] + curve + [(curve[-1][0], B)]
    g.polygon([(S(x), S(y)) for x, y in poly], fill=51)
    g.line([(S(x), S(y)) for x, y in curve], fill=0, width=S(3), joint="curve")

    # baseline + x axis: a tick every hour, a label every 3, day name at midnight
    g.line([(S(L), S(B)), (S(R), S(B))], fill=0, width=S(2))
    t = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while t <= end:
        x = xpx(t)
        major = t.hour % 3 == 0
        g.line([(S(x), S(B)), (S(x), S(B + (10 if major else 5)))], fill=0, width=S(2 if major else 1))
        if t.hour == 0:
            g.line([(S(x), S(T)), (S(x), S(B))], fill=153, width=S(1))
            g.text((S(x + 6), S(T + 4)), t.strftime("%a"), font=font(16, True), fill=85)
        if major and x - L > 64:  # leave room for the "now" label
            g.text((S(x), S(B + 14)), f"{t:%H}", font=font(18), fill=0, anchor="ma")
        t += timedelta(hours=1)
    g.text((S(L), S(B + 14)), "now", font=font(18, True), fill=0, anchor="la")

    img = img.resize((W, H), Image.LANCZOS)
    if ROTATE:
        img = img.rotate(ROTATE, expand=True)
    # snap to the panel's 16 grey levels so the e-ink controller doesn't dither
    img = img.point(lambda v: (v + 8) // 17 * 17)
    tmp = out + ".tmp"
    img.save(tmp, "PNG", optimize=True)
    os.replace(tmp, out)  # atomic, so the Kindle never fetches half a file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", nargs="?", default=".")
    ap.add_argument("--demo", action="store_true", help="use synthetic data")
    ap.add_argument("--heartbeat", default=HEARTBEAT, help="nginx heartbeat log")
    a = ap.parse_args()
    load_config()
    failed = False
    for slug, (place, lat, lon) in LOCATIONS.items():
        now = datetime.now(ZoneInfo(TZ))
        try:
            pts, now, end = demo(now) if a.demo else fetch(now, lat, lon)
            render(pts, now, end, os.path.join(a.outdir, f"rain-{slug}.png"), place)
            if slug == KINDLE:
                render(pts, now, end, os.path.join(a.outdir, "kindle.png"), place,
                       battery(now, a.heartbeat))
        except Exception as e:  # one bad location shouldn't block the other
            print(f"{slug}: {e}", file=sys.stderr)
            failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
