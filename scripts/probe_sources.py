#!/usr/bin/env python3
"""Probe v3 — validate CarGurus SEO URLs (model code + location code) from a runner.

v2 showed CarGurus answers a runner with 200 but geo-defaults to Cheyenne WY and
ignores unknown model ids. The real shape is /Cars/l-Used-<Make>-<Model>-<City>-d<model>_L<loc>,
e.g. d1037 = Panamera, L2793 = San Francisco. If that returns Panamera-priced
listings from the runner, the asking side can move to CarGurus with no API key.
"""
import re, ssl, statistics, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"}
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
# CarGurus embeds each listing as JSON with an integer "price" field
JPRICE = re.compile(r'"price"\s*:\s*([0-9]{4,7})(?:\.0)?\b')
TXTPRICE = re.compile(r"\$\s?([0-9]{2,3},[0-9]{3})")

T = [
 ("Panamera SF",   "https://www.cargurus.com/Cars/l-Used-Porsche-Panamera-San-Francisco-d1037_L2793"),
 ("Panamera natl", "https://www.cargurus.com/Cars/l-Used-Porsche-Panamera-d1037"),
 ("Pan Turbo trim","https://www.cargurus.com/Cars/t-Used-Porsche-Panamera-Turbo-t45354"),
]

for name, url in T:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HDRS),
                                    timeout=35, context=ssl.create_default_context()) as r:
            txt, code = r.read().decode("utf-8", "ignore"), r.status
            final = r.geturl()
    except urllib.error.HTTPError as e:
        txt, code, final = (e.read() or b"").decode("utf-8", "ignore"), e.code, url
    except Exception as e:
        print(f"{name:16} ERR {e.__class__.__name__}"); continue
    tm = TITLE.search(txt)
    title = re.sub(r"\s+", " ", tm.group(1)).strip()[:70] if tm else "(none)"
    j = sorted({int(x) for x in JPRICE.findall(txt) if 5000 <= int(x) <= 400000})
    t = sorted({int(x.replace(",", "")) for x in TXTPRICE.findall(txt)})
    print(f"\n{name:16} {code} {len(txt)/1024:.0f}KB")
    print(f"  title : {title}")
    print(f"  final : {final[:100]}")
    print(f"  json$ : n={len(j)} median={statistics.median(j) if j else '-'} sample={j[:8]}")
    print(f"  text$ : n={len(t)} sample={t[:8]}")
