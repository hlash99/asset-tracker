#!/usr/bin/env python3
"""Daily GitHub Actions refresh — best-effort asking prices for every asset
that carries a `ci` block in data.json: Cars.com medians for the cars, and
(since 2026-07-20) Chrono24 lowest-credible asks for the watches
(`ci.type == "chrono24"`). The 12Cilindri group and the personalized 997.2
FMV are NOT touched here — those only move when the local trackers publish.

Resilient by design: if a source blocks the runner or returns too few prices,
that asset keeps its last-good point. Run by .github/workflows/refresh.yml.
"""
import json, os, re, statistics, sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
PRICE_RE = re.compile(r"\$([0-9]{2,3},[0-9]{3})")
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
VIEWPORT = {"width": 1400, "height": 1000}


def prices_in_window(html, lo, hi):
    out = []
    for m in PRICE_RE.findall(html):
        v = int(m.replace(",", "")) / 1000.0   # -> $000s
        if lo <= v <= hi:
            out.append(v)
    return out


def value_n_days_ago(series, days):
    if not series:
        return None
    cutoff = (datetime.strptime(series[-1]["date"], "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    prior = [p for p in series if p["date"] <= cutoff]
    return prior[-1]["price"] if prior else None


def pct(cur, base):
    return round((cur / base - 1) * 100, 1) if (cur and base) else None


BAT_JSON_RE = re.compile(r"auctionsCompletedInitialData\s*=\s*(\{.*?\});", re.S)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def bat_recent_sold(page, bat):
    """Median of recent Bring a Trailer SOLD results for a `bat` block.

    Reserve-not-met ('Bid to') results are excluded. Titles are filtered by
    include/exclude keyword lists and an optional model-year range, prices by
    the lo/hi window ($k, same convention as `ci`). The window widens until it
    has enough sales: 90d needs 3, 180d needs 2, 365d takes 1.
    """
    page.goto(bat["url"], wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    m = BAT_JSON_RE.search(page.content())
    if not m:
        return None
    items = json.loads(m.group(1)).get("items", [])
    inc = [w.lower() for w in bat.get("include", [])]
    exc = [w.lower() for w in bat.get("exclude", [])]
    now = datetime.now(timezone.utc).timestamp()
    sold = []
    for it in items:
        title = it.get("title") or ""
        tl = title.lower()
        st = it.get("sold_text") or ""
        if "sold for" not in st.lower():
            continue                                  # reserve not met / withdrawn
        if inc and not all(w in tl for w in inc):
            continue
        if any(w in tl for w in exc):
            continue
        ym = YEAR_RE.search(title)
        if ym and not (bat.get("year_min", 0) <= int(ym.group(0)) <= bat.get("year_max", 9999)):
            continue
        pm = re.search(r"\$([0-9,]+)", st)
        ts = it.get("timestamp_end") or 0
        if not pm or not ts:
            continue
        v = int(pm.group(1).replace(",", ""))
        if not (bat["lo"] <= v / 1000.0 <= bat["hi"]):
            continue
        sold.append((ts, v, it))
    for days, need in ((90, 3), (180, 2), (365, 1)):
        w = [(ts, v, it) for ts, v, it in sold if now - ts <= days * 86400]
        if len(w) >= need:
            ts, v, it = max(w)                      # newest sale in the window → the linkable comp
            return {"median": round(statistics.median([x[1] for x in w])), "n": len(w),
                    "days": days, "updated": TODAY, "src": "bat",
                    "latest": {"url": it.get("url"), "title": it.get("title"), "price": v,
                               "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")}}
    return None


# One price per listing card, keyed by the listing id in the href (each card
# carries 2+ anchors to the same listing, so a page-wide regex double-counts).
CHRONO24_JS = """
() => {
  const out = {};
  for (const a of document.querySelectorAll("a[href*='--id']")) {
    const idm = a.href.match(/--id(\\d+)/);
    if (!idm) continue;
    const pm = a.innerText.match(/\\$\\s?([0-9][0-9,]{4,})/);
    if (pm && !(idm[1] in out)) out[idm[1]] = parseInt(pm[1].replace(/,/g, ''));
  }
  return out;
}
"""


def chrono24_prices(browser, ci):
    """Per-listing asks (raw dollars, ascending) from a Chrono24 search page.

    Fresh context per call: the second navigation in a shared context reliably
    trips Cloudflare's challenge, while a fresh one sails through. If challenged
    anyway, the challenge JS gets up to 20s to clear itself.
    """
    ctx = browser.new_context(user_agent=UA, viewport=VIEWPORT, locale="en-US")
    page = ctx.new_page()
    try:
        page.goto(ci["url"], wait_until="domcontentloaded", timeout=60000)
        for _ in range(10):
            if "just a moment" not in (page.title() or "").lower():
                break
            page.wait_for_timeout(2000)
        page.wait_for_timeout(3500)
        listing = page.evaluate(CHRONO24_JS)
    finally:
        ctx.close()
    return sorted(v for v in listing.values() if ci["lo"] <= v / 1000.0 <= ci["hi"])


def watch_headline(vals):
    """Headline = lowest credible ask — the local Selenium tracker's rule:
    MAD-filter outliers, then take the lowest unless it sits >8% below the
    second-lowest (a likely mispriced/gray listing), in which case take that."""
    med = statistics.median(vals)
    mad = statistics.median([abs(v - med) for v in vals])
    kept = sorted(v for v in vals
                  if mad == 0 or abs(0.6745 * (v - med) / mad) <= 3.5) or [round(med)]
    if len(kept) >= 2 and (kept[1] - kept[0]) / kept[0] > 0.08:
        return kept[1]
    return kept[0]


# Headline value: sold-weighted blend. Transactions beat asking prices (dealer asks
# on these cars run +10-46% over hammer), so the sold median dominates — weighted by
# how fresh the sold window is. Assets with no sold data fall back to the ask.
SOLD_WEIGHT = {90: 0.75, 180: 0.65, 365: 0.50}


def blended_value(a):
    s = a.get("sold")
    if s and s.get("median"):
        w = SOLD_WEIGHT.get(s.get("days"), 0.5)
        a["value"] = round(w * s["median"] + (1 - w) * a["latest"])
        a["value_note"] = f"{int(w*100)}% sold ({s['days']}d) + {int((1-w)*100)}% asking"
    else:
        a["value"] = a["latest"]
        a["value_note"] = "asking median (no recent sold data)"


def main():
    with open(DATA) as f:
        d = json.load(f)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("Playwright unavailable:", e); return 0

    log, changed = [], False
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(user_agent=UA, viewport=VIEWPORT)
        page = ctx.new_page()
        for a in d["assets"]:
            # ── BaT sold-results median (assets with a `bat` block) ──
            bat = a.get("bat")
            if bat:
                try:
                    s = bat_recent_sold(page, bat)
                    if s:
                        if s != a.get("sold"):
                            changed = True
                        a["sold"] = s
                        ser = a.setdefault("sold_series", [])
                        pt = {"date": TODAY, "price": s["median"], "n": s["n"], "days": s["days"]}
                        if ser and ser[-1]["date"] == TODAY:
                            ser[-1] = pt
                        else:
                            ser.append(pt)
                        log.append(f"{a['short']}: BaT sold median ${s['median']:,} (n={s['n']} in {s['days']}d)")
                    else:
                        log.append(f"{a['short']}: no matching BaT solds — kept last-known")
                except Exception as e:
                    log.append(f"{a['short']}: BaT failed ({e.__class__.__name__}) — kept last-known")

            ci = a.get("ci")
            if not ci:
                continue
            try:
                if ci.get("type") == "chrono24":
                    vals_usd = chrono24_prices(browser, ci)
                    if len(vals_usd) < ci.get("min_n", 3):
                        log.append(f"{a['short']}: only {len(vals_usd)} listings — kept last-good ${a['latest']:,}")
                        continue
                    # perrun semantics (same as the local CSVs): headline =
                    # lowest credible ask, band = raw min/max of the sample
                    price, lo, hi = watch_headline(vals_usd), vals_usd[0], vals_usd[-1]
                    vals = vals_usd
                else:
                    page.goto(ci["url"], wait_until="domcontentloaded", timeout=60000)
                    try:
                        page.wait_for_selector("[data-test='vehicleCard'], .vehicle-card, [class*='listing']", timeout=15000)
                    except Exception:
                        pass
                    page.wait_for_timeout(2500)
                    vals = prices_in_window(page.content(), ci["lo"], ci["hi"])
                    # min_n: rare variants (e.g. the ~100 US manual V12 Vantage S coupes)
                    # legitimately have 1-2 national listings, so 3 would freeze them forever
                    if len(vals) < ci.get("min_n", 3):
                        log.append(f"{a['short']}: only {len(vals)} prices — kept last-good ${a['latest']}k")
                        continue
                    price = round(statistics.median(vals) * 1000)
                    lo = round(sorted(vals)[max(0, int(0.25 * (len(vals) - 1)))] * 1000)
                    hi = round(sorted(vals)[min(len(vals) - 1, int(0.75 * (len(vals) - 1)))] * 1000)
                pt = {"date": TODAY, "price": price, "n": len(vals), "lo": lo, "hi": hi, "src": "ci"}
                s = a["series"]
                if s and s[-1]["date"] == TODAY:
                    s[-1] = pt
                else:
                    s.append(pt)
                a["latest"], a["n_listings"] = price, len(vals)
                a["range_lo"], a["range_hi"], a["updated"] = lo, hi, TODAY
                a["points"] = len(s)
                a["change"] = {
                    "d7": pct(price, value_n_days_ago(s, 7)),
                    "d30": pct(price, value_n_days_ago(s, 30)),
                    "d90": pct(price, value_n_days_ago(s, 90)),
                    "all": pct(price, s[0]["price"]),
                }
                changed = True
                stat = "lowest ask" if ci.get("type") == "chrono24" else "median"
                log.append(f"{a['short']}: n={len(vals)} {stat} ${price:,}")
            except Exception as e:
                log.append(f"{a['short']}: failed ({e.__class__.__name__}) — kept last-good")
        browser.close()

    for a in d["assets"]:
        blended_value(a)
    if changed:
        d["summary"]["portfolio_value"] = sum(a.get("value", a["latest"]) for a in d["assets"])
    d["updated"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with open(DATA, "w") as f:
        json.dump(d, f, indent=2)
    print("\n".join(log) or "no CI-enabled assets")
    print("changed:", changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
