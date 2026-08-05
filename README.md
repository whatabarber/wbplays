# Whatabarber Plays — deploy guide

Free, self-updating options dashboard. 4 files, no paid APIs, no keys.

## Files in this package
- `index.html` — the page itself (fetches `data.json` on load)
- `data.json` — your watchlist data (price, levels, verdicts, "why" text)
- `fetch_data.py` — pulls fresh price / 1-month change / implied vol via `yfinance` and rewrites `data.json`
- `update.yml` — GitHub Action that runs `fetch_data.py` daily and commits the result (**this file must end up at `.github/workflows/update.yml`** in your repo, not the root)

## 1. Create the repo
1. Go to github.com → **New repository**
2. Name it whatever you want, e.g. `whatabarber-plays`
3. Public, no README/gitignore needed (we're uploading everything)
4. Create it

## 2. Upload the files
1. On the repo page, click **Add file → Upload files**
2. Drag in `index.html`, `data.json`, and `fetch_data.py` — commit to `main`
3. Now the workflow file needs its own folder path:
   - Click **Add file → Create new file**
   - Name it exactly: `.github/workflows/update.yml` (typing the slashes creates the folders)
   - Paste in the contents of `update.yml`
   - Commit to `main`

## 3. Turn on GitHub Pages
1. Repo → **Settings → Pages**
2. Under "Build and deployment," Source = **Deploy from a branch**
3. Branch = `main`, folder = `/ (root)` → **Save**
4. GitHub gives you a URL like `https://yourusername.github.io/whatabarber-plays/` — takes 1-2 minutes to go live the first time

## 4. Run the data refresh once (don't wait for the schedule)
1. Repo → **Actions** tab
2. Click **Update market data** in the left sidebar
3. Click **Run workflow → Run workflow**
4. Wait ~30-60 seconds, refresh the page — you should see a green checkmark
5. Confirm `data.json` in the repo now shows today's date at the top

After that it runs automatically every weekday morning (12:30 UTC) with no action needed from you — you'll see a new green run in the Actions tab each day, and `data.json`'s "updated" date will bump.

## 5. Verify it
Open your Pages URL on your phone:
- Both Calls and Puts toggle states show a verdict for all 5 tickers
- Tap "Try a price," type a strike/expiry/premium → breakeven + fair value populate
- Tap "Live chart" on any card → TradingView loads
- Footer shows the disclaimer + refreshed date

## Updating your read on a stock
`fetch_data.py` only touches price, 1-month change, range position, and implied vol — it never overwrites your verdicts, "why" bullets, or support/resistance levels. When your thesis on a name changes, edit `data.json` directly (verdict is one of `go` / `wait` / `skip` / `mute`) and commit — that's it, no code changes needed.

## Adding/removing tickers
Add or remove an entry in the `names` array in `data.json` (copy an existing one as a template), and add/remove the matching line in the `TV` object near the top of the `<script>` in `index.html` (that's the TradingView symbol mapping, e.g. `NASDAQ:AAPL`).
