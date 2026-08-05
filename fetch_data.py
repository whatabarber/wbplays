"""
Whatabarber Plays — daily data refresh.

Pulls fresh price, 1-month % change, 52-week range position, and ATM implied
volatility (near + ~1mo-out expiry) for each ticker in data.json, using
yfinance (free, no API key). Verdicts / "why" text / support-resistance
levels are hand-written and are NOT touched by this script — edit those
directly in data.json when your read on a name changes.

Run locally:  pip install yfinance && python fetch_data.py
Run in CI:    see .github/workflows/update.yml
"""
import json
import datetime
import sys

import yfinance as yf


def atm_iv(ticker, expiry, spot):
    """Return implied vol of the call closest to the money for one expiry."""
    try:
        chain = ticker.option_chain(expiry)
        calls = chain.calls
        if calls.empty:
            return None
        calls = calls.copy()
        calls["diff"] = (calls["strike"] - spot).abs()
        row = calls.sort_values("diff").iloc[0]
        iv = float(row["impliedVolatility"])
        return iv if iv > 0 else None
    except Exception as e:
        print(f"  iv lookup failed for {expiry}: {e}", file=sys.stderr)
        return None


def refresh_one(name):
    sym = name["sym"]
    print(f"Fetching {sym}...")
    tk = yf.Ticker(sym)

    hist = tk.history(period="3mo")
    if hist.empty:
        print(f"  no price history for {sym}, skipping", file=sys.stderr)
        return

    spot = float(hist["Close"].iloc[-1])
    # 1-month change: compare to the close ~21 trading days back
    lookback = hist["Close"].iloc[-22] if len(hist) > 22 else hist["Close"].iloc[0]
    chg1m = (spot - float(lookback)) / float(lookback) * 100

    hist_1y = tk.history(period="1y")
    hi52 = float(hist_1y["High"].max()) if not hist_1y.empty else spot
    lo52 = float(hist_1y["Low"].min()) if not hist_1y.empty else spot
    range_pct = 0.0 if hi52 == lo52 else (spot - lo52) / (hi52 - lo52) * 100

    name["spot"] = round(spot, 2)
    name["price"] = f"${spot:,.2f}"
    name["chg"] = f"{'+' if chg1m >= 0 else ''}{chg1m:.1f}% \u00b7 1mo"
    name["dir"] = "up" if chg1m >= 0 else "down"

    # keep any hand-written Support/Resistance/Earnings level labels; only
    # refresh a level literally labeled "Range"
    for lv in name.get("levels", []):
        if lv[0] == "Range":
            lv[1] = f"{range_pct:.0f}% of 52wk"

    try:
        expiries = tk.options
    except Exception as e:
        expiries = []
        print(f"  no options chain for {sym}: {e}", file=sys.stderr)

    if expiries:
        near_iv = atm_iv(tk, expiries[0], spot)
        far_idx = min(3, len(expiries) - 1)
        far_iv = atm_iv(tk, expiries[far_idx], spot)
        if near_iv:
            name["ivNear"] = round(near_iv, 3)
        if far_iv:
            name["ivFar"] = round(far_iv, 3)


def main():
    with open("data.json") as f:
        data = json.load(f)

    for name in data["names"]:
        refresh_one(name)

    data["updated"] = datetime.date.today().isoformat()

    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)

    print("data.json updated.")


if __name__ == "__main__":
    main()
