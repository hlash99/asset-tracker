# asset-tracker

Interactive dashboard for my collector-asset price trackers — live at
**https://hlash99.github.io/asset-tracker/** and linked from the
[hlash99 dashboard](https://hlash99.github.io/).

It publishes the historical + current results of `run_trackers.py` as an
interactive page instead of a static PDF:

- **Watches** — Rolex GMT-Master II 126719BLRO Meteorite, Patek 5326G (Chrono24)
- **Cars** — Porsche 997.2 Turbo S (live asking tracker), plus every collector car on
  [car-value-tracker](https://hlash99.github.io/car-value-tracker/) mirrored in by
  `scripts/sync_cvt.py` (Ferraris, Lamborghinis, Acura, Audi, Lotus, Ford GT, Viper,
  Chevrolet Corvette C8 Z06, ...) as BaT sold medians
- **My 997.2 Turbo S** — personalized fair-market value with sold-comp percentile band

## How it updates

| Path | What | Trigger |
|------|------|---------|
| **Local publish** | All assets, full real history | `python3 run_trackers.py all` auto-runs `publish_trackers.py --push` at the end (or run `publish_trackers.py --push` directly). |
| **Daily CI** | CarGurus asking medians for all 9 CI-enabled cars + BaT sold medians | `.github/workflows/refresh.yml`, twice daily — best-effort, keeps last-good on failure. |
| **Local refresh** | Same as CI, plus the two Chrono24 watches | `python3 scripts/ci_refresh.py --push` — Chrono24 and cars.com serve a Cloudflare interstitial to datacenter IPs but answer a home connection, so a local run is the only way the watches move. `--push` commits and pushes `data.json`; without it the run only rewrites the file locally. |

## How the numbers are derived

- **CarGurus asks are smoothed.** One CarGurus page is a small, reshuffled sample, so the
  daily median swings 6-12% with no market move behind it. The ask used in the headline
  (`ask_smooth`) and in the 7/30/90-day chips is the median of the last 7 daily readings
  (none older than 14 days). Walk-forward on the stored history, predicting the next
  reading from the past only, this cut mean error on 4 of the 5 CarGurus cars
  (R8 16.3% to 10.1%, 992 GT3 Touring 5.9% to 4.5%, 991.1 GTS 8.5% to 6.9%, V12 Vantage S
  15.6% to 13.1%) and tied on the fifth. The same test favours the *last* reading for the
  Chrono24 watches and the locally published trackers, so those are not smoothed. Raw
  daily readings stay in `series` and are drawn as the faint line.
- **What moved.** Every run appends to each asset's `value_log` when its headline `value`
  changes. The "What moved" panel and the 7/30/90-day chips on the mirrored cars read it,
  and only report a window the log actually covers. Seeded from this repo's git history
  (own trackers from 2026-07-28, mirrored cars from 2026-10-31, when they switched to
  car-value-tracker's recent-sales value). A move on a mirrored car can be a new sale
  entering car-value-tracker's latest-N window or a change in its method - the card's
  value tooltip says which sales the figure rests on.
- **Mirror safety.** `sync_cvt.py` skips the run (exit 0, data untouched) if
  car-value-tracker cannot be fetched or looks truncated, and refuses to prune more than a
  quarter of the mirrored cars at once.

`data.json` is the single source of truth; `index.html` (Chart.js, no build step)
renders it. The local builder lives in `../publish_trackers.py`.
