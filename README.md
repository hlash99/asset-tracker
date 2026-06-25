# asset-tracker

Interactive dashboard for my collector-asset price trackers — live at
**https://hlash99.github.io/asset-tracker/** and linked from the
[hlash99 dashboard](https://hlash99.github.io/).

It publishes the historical + current results of `run_trackers.py` as an
interactive page instead of a static PDF:

- **Watches** — Rolex GMT-Master II 126719BLRO Meteorite, Patek 5326G (Chrono24)
- **Cars** — Ferrari 458 Italia, 812 Superfast, 812 GTS, 12Cilindri, Porsche 997.2 Turbo S
- **My 997.2 Turbo S** — personalized fair-market value with sold-comp percentile band

## How it updates

| Path | What | Trigger |
|------|------|---------|
| **Local publish** | All assets, full real history | `python3 run_trackers.py all` auto-runs `publish_trackers.py --push` at the end (or run `publish_trackers.py --push` directly). |
| **Daily CI** | Cars.com asking medians for the CI-enabled Ferraris (458, 812 Superfast) | `.github/workflows/refresh.yml`, twice daily — best-effort, keeps last-good on failure. |

`data.json` is the single source of truth; `index.html` (Chart.js, no build step)
renders it. The local builder lives in `../publish_trackers.py`.
