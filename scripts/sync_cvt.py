#!/usr/bin/env python3
"""Mirror the car-value-tracker's collector cars into this dashboard.

The two pages had drifted: car-value-tracker carried fourteen cars, this one
carried five of them. Rather than re-scrape Bring a Trailer here -- which is
how they diverged in the first place -- this pulls the already-published
car-value-tracker data.json and upserts each car as an asset. One source of
truth, so the two dashboards cannot disagree about a price again.

Cars ALREADY tracked here with their own live source are left alone (see
SKIP): this page's 997.2 Turbo S is a live asking tracker that also feeds the
personal block, and its Audi R8 is deliberately broader in scope (all
transmissions, both bodies) than car-value-tracker's gated-manual-only R8 --
so the gated car is mirrored in as a SEPARATE asset rather than overwriting it.

The mirrored series is ANNUAL: one point per calendar year, the median of that
year's BaT sold prints, with the interquartile band. That is a different shape
to the near-daily asking series the scraped assets carry, which is why each
mirrored asset declares `series_label` and `n_label` for the UI to read.

Stdlib only. Runs before ci_refresh.py in the refresh workflow.
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

CVT_URL = "https://hlash99.github.io/car-value-tracker/data.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Already tracked here from a live source of their own -- do not mirror.
SKIP = {
    "Porsche 997.2 Turbo S",          # -> porsche_997_turbo_s (live asking + personal block)
    "Ferrari 458 Italia",             # -> ferrari_458_italia
    "Ferrari 812 Superfast",          # -> ferrari_812_superfast
    "Ferrari 812 GTS",                # -> ferrari_812_gts
}

# Every mirrored car must match one of these or it lands in the "Other" block,
# which this dashboard deliberately no longer has — add the marque when adding a car.
MAKES = [("Acura", "Acura"), ("Ferrari", "Ferrari"), ("Audi", "Audi"),
         ("Porsche", "Porsche"), ("Volvo", "Volvo"), ("Alfa Romeo", "Alfa Romeo"),
         ("Corvette", "Chevrolet"), ("Lotus", "Lotus")]

# Short card labels; anything unlisted falls back to the full name.
SHORT = {
    "Acura NSX (NA2 manual)": "NSX (NA2 manual)",
    "Ferrari 360 (gated manual)": "360 gated manual",
    "Audi R8 gen1 V10 (gated)": "R8 gen1 V10 gated",
    "Corvette split-window (1963)": "'63 split-window",
    "Volvo P1800 (1800 family)": "P1800",
    "Alfa Romeo GTV 1750/2000": "GTV 1750/2000",
    "Porsche Singer 911": "Singer 911",
    "Ferrari 328 GTS/GTB": "328 GTS/GTB",
    "Ferrari Dino 246 GT/GTS": "Dino 246",
    "Ferrari F12 Berlinetta": "F12 Berlinetta",
    "Lotus Evora GT (2020-21)": "Evora GT",
}

NOTE_EXTRA = {
    # The one place the two dashboards legitimately disagree, stated on the card.
    "Audi R8 gen1 V10 (gated)":
        " Gated manual coupe only - the broader 'R8 V10 Gen 1' card on this page "
        "includes R-tronic/S-tronic and the Spyder, and prices lower as a result.",
}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def make_of(name):
    for needle, mk in MAKES:
        if needle.lower() in name.lower():
            return mk
    return "Other"


def pct(cur, base):
    return None if not base else round((cur / base - 1) * 100, 1)


def build_series(car, years):
    """Annual points in whole dollars. Prefers the real per-year BaT detail
    (median + n + quartile band); falls back to the dashboard `hist` for the
    Cars.com cars, which have no per-year sample to report."""
    ann = car.get("annual")
    if ann:
        out = []
        for i, p in enumerate(ann):
            date = TODAY if i == len(ann) - 1 else f"{p['year']}-12-31"
            out.append({"date": date, "price": round(p["median"] * 1000),
                        "n": p["n"], "lo": round(p["lo"] * 1000), "hi": round(p["hi"] * 1000)})
        return out, True
    hist = car.get("hist") or []
    out = []
    for i, (y, v) in enumerate(zip(years, hist)):
        date = TODAY if i == len(hist) - 1 else f"{y}-12-31"
        px = round(v * 1000)
        out.append({"date": date, "price": px, "n": None, "lo": px, "hi": px})
    return out, False


def upsert(d, name, car, years):
    series, is_bat = build_series(car, years)
    if len(series) < 2:
        return None
    key = slug(name)
    latest, first = series[-1]["price"], series[0]["price"]
    by_key = {a["key"]: a for a in d["assets"]}
    a = by_key.get(key) or {"key": key}

    note = (car.get("blurb") or "").strip()
    note += NOTE_EXTRA.get(name, "")
    a.update({
        "name": name,
        "short": SHORT.get(name, name),
        "category": "car",
        "make": make_of(name),
        "color": car.get("color", "#888"),
        "source": ("Bring a Trailer sold comps (via car-value-tracker)" if is_bat
                   else "Cars.com asking (via car-value-tracker)"),
        "note": note,
        "currency": "USD",
        "updated": TODAY,
        "start": series[0]["date"],
        "latest": latest,
        "first": first,
        # None, not 0: the Cars.com-derived mirrors have a reconstructed annual
        # history with no per-year sample to report, and "0 listings" reads as
        # a scrape failure rather than "not applicable".
        "n_listings": car.get("n_comps") or series[-1].get("n") or None,
        "range_lo": min(p["lo"] for p in series),
        "range_hi": max(p["hi"] for p in series),
        # Annual data cannot support 7/30/90-day deltas; the UI renders null as
        # an em dash rather than inventing a number.
        "change": {"d7": None, "d30": None, "d90": None,
                   "all": pct(latest, first)},
        "points": len(series),
        "series": series,
        "series_label": "BaT sold median" if is_bat else "asking median",
        "n_label": "sold comps" if is_bat else "listings",
        "value": latest,
        "value_note": ("Median of this year's BaT sold prints"
                       if is_bat else "Cars.com asking median"),
        # One point per calendar year. The group aggregate must not read a
        # year-on-year step as a 7-day move, so it is told the cadence.
        "cadence": "annual",
        "mirrored_from": "car-value-tracker",
    })
    if key not in by_key:
        d["assets"].append(a)
    return key, len(series), latest


def main():
    with open(DATA) as f:
        d = json.load(f)
    cvt = json.loads(urllib.request.urlopen(
        urllib.request.Request(CVT_URL, headers={"User-Agent": "asset-tracker-sync"}),
        timeout=60).read().decode())
    years = cvt["years"]

    log = []
    for name, car in cvt["cars"].items():
        if name in SKIP:
            continue
        r = upsert(d, name, car, years)
        log.append(f"{name}: {r[1]}pts, ${r[2]:,}" if r else f"{name}: SKIPPED (thin series)")

    cars = [a for a in d["assets"] if a.get("category") == "car"]
    d.setdefault("summary", {})
    d["summary"]["n_assets"] = len(d["assets"])
    d["summary"]["n_cars"] = len(cars)
    d["summary"]["n_watches"] = len([a for a in d["assets"] if a.get("category") == "watch"])
    d["summary"]["portfolio_value"] = round(sum(a.get("value") or a.get("latest") or 0
                                                for a in d["assets"]))
    d["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d["cvt_sync"] = " | ".join(log)
    with open(DATA, "w") as f:
        json.dump(d, f, indent=1)
    print("\n".join(log))
    print(f"\n{len(d['assets'])} assets ({len(cars)} cars)")


if __name__ == "__main__":
    main()
