# Whatabarber Plays — technical dashboard (v2)

Free, self-updating options dashboard. Verdicts, support/resistance, trend,
and "why" text are now all **computed from real price history** — nothing
in this version is hand-typed analysis.

## What's actually computed, every day, automatically
- Price, 1-month % change, position in 52-week range
- 20-day / 50-day moving averages → trend (up / down / range-bound)
- 14-day RSI → momentum
- 20-day swing support/resistance (real rolling high/low, not guesses)
- Previous-day high/low (PDH/PDL) — same concept as your Pine Script's
  breakout box, computed daily here instead of intraday
- Next earnings date (if within 14 days) — forces "Track only" regardless
  of technicals, since binary risk overrides a clean setup
- Implied vol (for the Black-Scholes "Try a price" analyzer)
- Call/put verdicts and the "why" bullets — built from a fixed rule set
  applied to the numbers above (see `fetch_data.py` header comment for the
  exact rules)

## What's still NOT automated (and can't be, for free)
Real news/catalyst judgment — "why did this actually move" beyond what a
confirmed earnings date tells you. That requires either a paid news API or
a human reading the news. This version doesn't pretend otherwise.

## Files
- `index.html` — the page (fetches `data.json`, includes a live-ticking
  clock, a computed trend-snapshot strip, and an "Open on TradingView.com
  — use my saved indicators" link on every chart)
- `data.json` — minimal seed (just ticker + company name); the daily Action
  fills in every other field
- `fetch_data.py` — does all the computation described above
- `update.yml` — goes at `.github/workflows/update.yml`; unchanged from
  before, still runs weekdays + on-demand

## Deploy / update steps (same as before)
1. On GitHub, open each file (`index.html`, `data.json`, `fetch_data.py`) →
   pencil icon → select all → paste the new version → commit
2. Go to **Actions → Update market data → Run workflow** — do this once
   right after pushing, since the seed `data.json` has no computed fields
   yet and the page will show a "waiting on first data run" notice until
   it does
3. Confirm the run is green, then reload the live page

## Adding a ticker
Add `{"sym": "XYZ", "co": "Company Name"}` to the `names` array in
`data.json`, plus the matching TradingView symbol (e.g. `NASDAQ:XYZ`) to
the `TV` object near the top of the `<script>` in `index.html`. Run the
Action once to populate it.

## Tuning the verdict rules
Everything lives in `fetch_data.py`: `classify_trend()`, `rsi_state()`, and
`verdict_for()`. E.g. to make it less conservative near resistance, change
the `0.02` (2%) threshold in `verdict_for()`. No other file needs to change.
