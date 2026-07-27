#!/usr/bin/env python3
"""One-off probe: which listing sources answer a GitHub Actions runner?

cars.com and chrono24 both serve the runner a Cloudflare interstitial
("Just a moment...", ~8KB) so the asking-price side of the tracker has been
frozen. This tries a spread of alternatives with plain HTTP first, since a
datacenter IP with a believable UA is often fine where headless Chromium is
not. Prints a table; nothing here writes data.json.
"""
import json, re, ssl, sys, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"}
PRICE = re.compile(r"\$\s?([0-9]{2,3},[0-9]{3})")
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)

TARGETS = [
  ("cars.com BASELINE",      "https://www.cars.com/shopping/results/?stock_type=used&makes[]=porsche&models[]=porsche-panamera&year_min=2018&year_max=2020&maximum_distance=all&zip=94027"),
  ("chrono24 BASELINE",      "https://www.chrono24.com/search/index.htm?currencyId=USD&dosearch=true&pageSize=60&query=Patek+Philippe+5326G&sortorder=1"),
  ("bringatrailer BASELINE", "https://bringatrailer.com/porsche/panamera/"),
  ("autotrader",             "https://www.autotrader.com/cars-for-sale/porsche/panamera"),
  ("cargurus",               "https://www.cargurus.com/Cars/l-Used-Porsche-Panamera-d842"),
  ("truecar",                "https://www.truecar.com/used-cars-for-sale/listings/porsche/panamera/"),
  ("edmunds",                "https://www.edmunds.com/porsche/panamera/2019/"),
  ("carvana",                "https://www.carvana.com/cars/porsche-panamera"),
  ("hemmings",               "https://www.hemmings.com/classifieds/cars-for-sale/porsche/panamera"),
  ("classic.com",            "https://www.classic.com/m/porsche/panamera/"),
  ("carsandbids past",       "https://carsandbids.com/past-auctions/?q=panamera"),
  ("pcarmarket",             "https://www.pcarmarket.com/search/?q=panamera"),
  ("ebay motors search",     "https://www.ebay.com/sch/i.html?_nkw=porsche+panamera+sport+turismo&_sacat=6001"),
  ("ebay watches search",    "https://www.ebay.com/sch/i.html?_nkw=patek+philippe+5326g"),
  ("bobswatches",            "https://www.bobswatches.com/rolex/gmt-master-ii"),
  ("watchcharts",            "https://watchcharts.com/watches/brand/patek_philippe"),
  ("jomashop",               "https://www.jomashop.com/catalogsearch/result/?q=5326g"),
  ("autotempest",            "https://www.autotempest.com/results?make=porsche&model=panamera"),
]

def probe(name, url):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=HDRS)
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            body = r.read()
            code, final = r.status, r.geturl()
    except urllib.error.HTTPError as e:
        body, code, final = (e.read() or b""), e.code, url
    except Exception as e:
        return dict(name=name, code="ERR", note=e.__class__.__name__, n=0, size=0, title="")
    txt = body.decode("utf-8", "ignore")
    tm = TITLE.search(txt)
    title = re.sub(r"\s+", " ", tm.group(1)).strip()[:52] if tm else ""
    prices = PRICE.findall(txt)
    blocked = ("just a moment" in title.lower() or "attention required" in title.lower()
               or "access denied" in title.lower() or code in (403, 429))
    return dict(name=name, code=code, note="CLOUDFLARE/BLOCK" if blocked else "",
                n=len(prices), size=len(txt), title=title,
                sample=sorted({int(p.replace(",", "")) for p in prices})[:4])

print(f"{'source':24} {'code':>5} {'KB':>7} {'$hits':>6}  title / note")
print("-" * 108)
ok = []
for name, url in TARGETS:
    r = probe(name, url)
    flag = r["note"] or ("OK" if r["n"] >= 5 else "no prices")
    print(f"{r['name']:24} {str(r['code']):>5} {r['size']/1024:7.1f} {r['n']:>6}  {flag} | {r['title']}")
    if r.get("sample"):
        print(f"{'':24} {'':>5} {'':>7} {'':>6}    sample: {r['sample']}")
    if not r["note"] and r["n"] >= 5:
        ok.append(r["name"])
print("\nUSABLE (>=5 in-page prices, no block):", ", ".join(ok) or "none")
