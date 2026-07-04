#!/usr/bin/env python3
"""Daily GitHub Actions refresh — best-effort Cars.com asking medians for the
cars that carry a `ci` block in data.json (currently the Ferraris that scrape
reliably). Watches, the 12Cilindri group and the personalized 997.2 FMV are NOT
touched here — those only move when the local trackers run and publish.

Resilient by design: if a source blocks the runner or returns too few prices,
that asset keeps its last-good point. Run by .github/workflows/refresh.yml.
"""
import json, os, re, statistics, sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
PRICE_RE = re.compile(r"\$([0-9]{2,3},[0-9]{3})")
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
            viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        for a in d["assets"]:
            ci = a.get("ci")
            if not ci:
                continue
            try:
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
                log.append(f"{a['short']}: n={len(vals)} median ${price:,}")
            except Exception as e:
                log.append(f"{a['short']}: failed ({e.__class__.__name__}) — kept last-good")
        browser.close()

    if changed:
        d["summary"]["portfolio_value"] = sum(a["latest"] for a in d["assets"])
    d["updated"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with open(DATA, "w") as f:
        json.dump(d, f, indent=2)
    print("\n".join(log) or "no CI-enabled assets")
    print("changed:", changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
