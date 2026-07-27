#!/usr/bin/env python3
"""Probe v2 — pin down usable URL shapes on the two hosts that answered a runner.

Round 1 showed only bringatrailer and cargurus return real listing pages to a
GitHub runner; every other car/watch site returns a Cloudflare 403. bobswatches
served 185KB (just a 404 on my path), so it is reachable too. This round hunts
for URL shapes that return the RIGHT cars/watches, including CarGurus' JSON
inventory endpoint.
"""
import json, re, ssl, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"}
PRICE = re.compile(r"\$\s?([0-9]{2,3},[0-9]{3})")
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)

CG = "https://www.cargurus.com"
TARGETS = [
  ("CG json panamera",  CG+"/Cars/inventorylisting/ajaxFetchSubsetInventoryListing.action?sourceContext=carGurusHomePageModel&zip=94027&distance=50000&entitySelectingHelper.selectedEntity=d2260&startYear=2018&endYear=2020"),
  ("CG kw panamera st", CG+"/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action?zip=94027&distance=50000&searchId=&modelChanged=false&filtersModified=true&inventorySearchWidgetType=AUTO&entitySelectingHelper.selectedEntity=&keywordSearch=panamera+sport+turismo"),
  ("CG seo panamera",   CG+"/Cars/l-Used-Porsche-Panamera-c24743"),
  ("CG seo 911",        CG+"/Cars/l-Used-Porsche-911-c22703"),
  ("CG seo r8",         CG+"/Cars/l-Used-Audi-R8-c23241"),
  ("CG sitemap probe",  CG+"/Cars/l-Used-Porsche-Panamera"),
  ("bobs 126719blro",   "https://www.bobswatches.com/rolex-gmt-master-ii-126719blro.html"),
  ("bobs gmt listing",  "https://www.bobswatches.com/rolex-watches/gmt-master-ii-watches.html"),
  ("bobs search blro",  "https://www.bobswatches.com/catalogsearch/result/?q=126719BLRO"),
  ("watchfinder",       "https://www.watchfinder.com/search?q=5326G"),
  ("1916 company",      "https://www.the1916company.com/catalogsearch/result/?q=5326G"),
  ("crownandcaliber",   "https://www.crownandcaliber.com/collections/patek-philippe"),
  ("watchbox/1916 alt", "https://www.the1916company.com/shop/watches/patek-philippe"),
]

def probe(name, url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HDRS),
                                    timeout=30, context=ssl.create_default_context()) as r:
            body, code = r.read(), r.status
    except urllib.error.HTTPError as e:
        body, code = (e.read() or b""), e.code
    except Exception as e:
        print(f"{name:22} ERR  {e.__class__.__name__}"); return
    txt = body.decode("utf-8", "ignore")
    tm = TITLE.search(txt)
    title = re.sub(r"\s+", " ", tm.group(1)).strip()[:60] if tm else "(no title)"
    prices = sorted({int(p.replace(",", "")) for p in PRICE.findall(txt)})
    blocked = "just a moment" in title.lower() or "attention required" in title.lower() or code == 403
    tag = "BLOCK" if blocked else ("OK" if len(prices) >= 5 else "thin")
    print(f"{name:22} {code:>4} {len(txt)/1024:7.1f}KB {len(prices):>4}p  {tag:5} | {title}")
    if prices[:6]:
        print(f"{'':22}                            sample {prices[:6]}")

print(f"{'target':22} {'code':>4} {'size':>9} {'n':>5}  {'':5}   title")
print("-"*112)
for n, u in TARGETS:
    probe(n, u)
