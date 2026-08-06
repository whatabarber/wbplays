"""
Whatabarber Plays — technical dashboard data engine.

Every field in data.json is computed fresh from real price history each run —
support/resistance, trend, RSI momentum, verdicts, and the "why" bullets are
all derived from numbers, not hand-typed. Nothing here requires a paid API.

Computed per ticker:
  - spot, 1-month % change, 52-week range position   (as before)
  - 20-day / 50-day SMA -> trend classification (up / down / range)
  - 14-day RSI -> momentum state
  - 20-day swing support/resistance (rolling low/high, excluding today)
  - previous-day high/low (PDH/PDL) — same concept as the PDH/PDL breakout
    logic in your Pine Script indicator, just computed daily here instead of
    intraday on the 15-min chart
  - next confirmed earnings date (if within the next 14 days), which forces
    the verdict to "Track only" regardless of technicals — binary earnings
    risk overrides a clean technical setup
  - implied vol (ATM, near + ~1mo expiry) for the Black-Scholes analyzer

Verdict logic (call side; put side is the mirror):
  - trend == up, RSI is bullish/neutral, and price isn't already pinned
    against resistance  -> "go"
  - trend == up but RSI overbought or price within 2% of resistance -> "wait"
  - trend == down -> "skip"
  - trend == range (no clear MA structure) -> "wait"
  - earnings inside 14 days -> always "mute" ("Track only"), overriding
    the above, since premium is already pricing in binary risk

Run locally:  pip install yfinance && python fetch_data.py
Run in CI:    see .github/workflows/update.yml
"""
import json
import datetime
import sys

import numpy as np
import pandas as pd
import yfinance as yf


# ----------------------------------------------------------------------
# indicators
# ----------------------------------------------------------------------
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def rsi_state(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "neutral", "RSI unavailable (not enough price history yet)"
    if v >= 70:
        return "overbought", f"RSI(14) is {v:.0f} \u2014 overbought / extended, chasing here is late"
    if v <= 30:
        return "oversold", f"RSI(14) is {v:.0f} \u2014 oversold"
    if v >= 55:
        return "bullish", f"RSI(14) is {v:.0f} \u2014 neutral-to-bullish momentum"
    if v <= 45:
        return "bearish", f"RSI(14) is {v:.0f} \u2014 neutral-to-bearish momentum"
    return "neutral", f"RSI(14) is {v:.0f} \u2014 neutral, no clear momentum either way"


def classify_trend(spot, sma20, sma50):
    if any(x is None or np.isnan(x) for x in (spot, sma20, sma50)):
        return "range"
    if spot > sma50 and sma20 > sma50:
        return "up"
    if spot < sma50 and sma20 < sma50:
        return "down"
    return "range"


def swing_levels(hist, lookback=20):
    """Rolling support/resistance from the N trading days before today."""
    window = hist.iloc[-(lookback + 1):-1]
    if window.empty:
        window = hist
    return float(window["Low"].min()), float(window["High"].max())


def next_earnings_within(tk, days=14):
    try:
        cal = tk.get_earnings_dates(limit=6)
        if cal is None or cal.empty:
            return None
        now = pd.Timestamp.now(tz=cal.index.tz)
        future = cal[cal.index >= now]
        if future.empty:
            return None
        dt = future.index[0]
        if (dt - now).days <= days:
            return dt.strftime("%Y-%m-%d")
        return None
    except Exception as e:
        print(f"  earnings lookup failed: {e}", file=sys.stderr)
        return None


def verdict_for(direction, trend, rsi_lbl, spot, support, resistance, earnings):
    if earnings:
        vlabel = "Track only"
        return "mute", vlabel
    near_res = resistance and (resistance - spot) / spot < 0.02
    near_sup = support and (spot - support) / spot < 0.02
    if direction == "call":
        if trend == "up" and rsi_lbl in ("bullish", "neutral") and not near_res:
            return "go", "Looks solid"
        if trend == "up" and (rsi_lbl == "overbought" or near_res):
            return "wait", "Wait"
        if trend == "down":
            return "skip", "Skip"
        return "wait", "Wait"
    else:  # put
        if trend == "down" and rsi_lbl in ("bearish", "neutral") and not near_sup:
            return "go", "Looks solid"
        if trend == "down" and (rsi_lbl == "oversold" or near_sup):
            return "wait", "Wait"
        if trend == "up":
            return "skip", "Skip"
        return "wait", "Wait"


def build_why(direction, trend, rsi_text, spot, support, resistance, pdh, pdl, earnings):
    trend_word = {"up": "an uptrend (price above both the 20 & 50-day averages)",
                  "down": "a downtrend (price below both the 20 & 50-day averages)",
                  "range": "no clear trend (price is mixed against the 20/50-day averages)"}[trend]
    why = [["Trend", f"Currently in {trend_word}."],
           ["Momentum", rsi_text]]
    if direction == "call":
        dist = (resistance - spot) / spot * 100 if resistance else None
        lvl = f"Resistance ${resistance:.2f}" + (f" ({dist:.1f}% away)" if dist is not None else "")
        why.append(["Levels", f"{lvl}. Support ${support:.2f}. Prior day's range: ${pdl:.2f}\u2013${pdh:.2f}."])
    else:
        dist = (spot - support) / spot * 100 if support else None
        lvl = f"Support ${support:.2f}" + (f" ({dist:.1f}% away)" if dist is not None else "")
        why.append(["Levels", f"{lvl}. Resistance ${resistance:.2f}. Prior day's range: ${pdl:.2f}\u2013${pdh:.2f}."])
    if earnings:
        why.append(["Earnings", f"Next confirmed earnings date is {earnings} \u2014 inside 2 weeks. Premium already prices in binary risk; technicals take a back seat until after the print."])
    return why


def atm_iv(ticker, expiry, spot):
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


# ----------------------------------------------------------------------
# per-ticker refresh
# ----------------------------------------------------------------------
def refresh_one(entry):
    sym = entry["sym"]
    print(f"Fetching {sym}...")
    tk = yf.Ticker(sym)

    hist = tk.history(period="6mo")
    if hist.empty:
        print(f"  no price history for {sym}, skipping", file=sys.stderr)
        return

    spot = float(hist["Close"].iloc[-1])
    lookback_close = hist["Close"].iloc[-22] if len(hist) > 22 else hist["Close"].iloc[0]
    chg1m = (spot - float(lookback_close)) / float(lookback_close) * 100

    hist_1y = tk.history(period="1y")
    hi52 = float(hist_1y["High"].max()) if not hist_1y.empty else spot
    lo52 = float(hist_1y["Low"].min()) if not hist_1y.empty else spot
    range_pct = 0.0 if hi52 == lo52 else (spot - lo52) / (hi52 - lo52) * 100

    sma20 = float(hist["Close"].rolling(20).mean().iloc[-1]) if len(hist) >= 20 else None
    sma50 = float(hist["Close"].rolling(50).mean().iloc[-1]) if len(hist) >= 50 else None
    rsi_val = float(rsi(hist["Close"]).iloc[-1]) if len(hist) >= 15 else None

    support, resistance = swing_levels(hist, lookback=20)
    pdl = float(hist["Low"].iloc[-2]) if len(hist) > 1 else float(hist["Low"].iloc[-1])
    pdh = float(hist["High"].iloc[-2]) if len(hist) > 1 else float(hist["High"].iloc[-1])

    trend = classify_trend(spot, sma20, sma50)
    rsi_lbl, rsi_text = rsi_state(rsi_val)
    earnings = next_earnings_within(tk, days=14)

    entry["spot"] = round(spot, 2)
    entry["price"] = f"${spot:,.2f}"
    entry["chg"] = f"{'+' if chg1m >= 0 else ''}{chg1m:.1f}% \u00b7 1mo"
    entry["dir"] = "up" if chg1m >= 0 else "down"
    entry["trend"] = trend
    entry["levels"] = [["Support", f"${support:.2f}"],
                        ["Resistance", f"${resistance:.2f}"],
                        ["Range", f"{range_pct:.0f}% of 52wk"]]

    for direction in ("call", "put"):
        v, vlabel = verdict_for(direction, trend, rsi_lbl, spot, support, resistance, earnings)
        why = build_why(direction, trend, rsi_text, spot, support, resistance, pdh, pdl, earnings)
        entry[direction] = {"verdict": v, "vlabel": vlabel, "why": why}

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
            entry["ivNear"] = round(near_iv, 3)
        if far_iv:
            entry["ivFar"] = round(far_iv, 3)


def main():
    with open("data.json") as f:
        data = json.load(f)

    for entry in data["names"]:
        refresh_one(entry)

    data["updated"] = datetime.date.today().isoformat()
    data["analysis_date"] = data["updated"]  # verdicts are computed same-run now, always current

    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)

    print("data.json updated \u2014 all fields computed from live price history.")


if __name__ == "__main__":
    main()
