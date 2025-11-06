from flask import Flask, jsonify, render_template
import yfinance as yf
import pandas as pd
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

app = Flask(__name__)

# ----------------------------
# ROUTE 1: Serve the HTML page
# ----------------------------
@app.route("/")
def home():
    return render_template("index.html")

# ----------------------------
# STOCK LIST
# ----------------------------
NIFTY_100 = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
    "BHARTIARTL.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS"
]

# ----------------------------
# Utility: Fetch stock data
# ----------------------------
def get_stock_data(symbol):
    try:
        # Fetching 1 month of daily data
        df = yf.download(symbol, period="1mo", interval="1d", progress=False)
        if df.empty:
            print(f"[WARN] Empty data for {symbol}")
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        return df
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")
        return pd.DataFrame()

# ----------------------------
# ROUTE 2: Auto Trend Detector
# ----------------------------
@app.route("/api/auto_trends")
def auto_trends():
    results = []

    for symbol in NIFTY_100:
        df = get_stock_data(symbol)
        if df.empty or "Close" not in df.columns:
            continue

        df["Change"] = df["Close"].pct_change()
        streak = 0
        trend = None

        for i in range(1, len(df)):
            if df["Change"].iloc[i] < 0:
                streak = streak + 1 if trend == "fall" else 1
                trend = "fall"
            elif df["Change"].iloc[i] > 0:
                streak = streak + 1 if trend == "rise" else 1
                trend = "rise"
            else:
                streak = 0
                trend = None

            # Only look for streaks of 3 or more days
            if streak >= 3:
                # Include the last 7 days for the chart visualization
                recent = df.tail(7)
                results.append({
                    "symbol": symbol,
                    "streak_type": trend,
                    "days": streak,
                    "last_close": float(df["Close"].iloc[-1]),
                    "as_of": df.index[-1].strftime("%Y-%m-%d"),
                    "prices": recent["Close"].round(2).tolist(),
                    "dates": recent.index.strftime("%d-%b").tolist(),
                })
                break

    if not results:
        return jsonify({"error": "No trend data found"}), 400

    return jsonify(results)

# ----------------------------
# Utility: Calculate Momentum Data
# ----------------------------
def calculate_momentum_data(symbol_list, periods=5):
    results = []
    for symbol in symbol_list:
        df = get_stock_data(symbol)
        if df.empty or "Close" not in df.columns:
            continue

        # Calculate N-day (e.g., 5-day for 1 week) change
        df["change_pct"] = df["Close"].pct_change(periods=periods) * 100
        if df["change_pct"].dropna().empty:
            continue

        last_change = df["change_pct"].iloc[-1]
        results.append({
            "symbol": symbol,
            "change_pct": round(float(last_change), 2),
            "last_close": float(df["Close"].iloc[-1]),
            "as_of": df.index[-1].strftime("%Y-%m-%d")
        })

    if not results:
        return pd.DataFrame(), {"error": "No valid momentum data found"}

    df_results = pd.DataFrame(results)
    df_results["change_pct"] = pd.to_numeric(df_results["change_pct"], errors="coerce")
    df_results = df_results.dropna(subset=["change_pct"])

    if df_results.empty:
        return pd.DataFrame(), {"error": "No numeric momentum values"}

    df_results = df_results.sort_values(by="change_pct", ascending=False)
    return df_results, None

# ----------------------------
# ROUTE 3: Momentum Analyzer (All Stocks)
# ----------------------------
@app.route("/api/momentum")
def momentum_stocks():
    # Uses 5-day change by default for consistency with the new High/Low route
    df_results, error = calculate_momentum_data(NIFTY_100, periods=5)
    if error:
        return jsonify(error), 400

    # This route returns ALL results sorted
    return jsonify(df_results.to_dict(orient="records"))

# ----------------------------
# ROUTE 4: High/Low Performers (1-Week Low/High)
# ----------------------------
@app.route("/api/high_low_performers")
def high_low_performers():
    # Use 5-day period (1 week) for performance comparison
    periods = 5
    df_results, error = calculate_momentum_data(NIFTY_100, periods=periods)
    if error:
        return jsonify(error), 400

    # Get top N (High) and bottom N (Low) performers
    N = 3
    
    # Ensure we have at least N items for both
    if len(df_results) < N:
        N = len(df_results) // 2
    
    # Top N performers (High)
    high_performers = df_results.head(N).to_dict(orient="records")
    
    # Bottom N performers (Low)
    low_performers = df_results.tail(N).to_dict(orient="records")
    
    return jsonify({
        "high": high_performers,
        "low": low_performers,
        "period": f"{periods}-Day (1 Week)",
        "N": N
    })

# ... (continues from ROUTE 4: High/Low Performers)

# ----------------------------
# ROUTE 5: Moving Average (20-Day SMA) Analyzer - NEW ROUTE
# ----------------------------
@app.route("/api/moving_average")
def moving_average_stocks():
    results = []
    periods = 20 # 20-Day SMA

    for symbol in NIFTY_100:
        df = get_stock_data(symbol)
        if df.empty or "Close" not in df.columns:
            continue

        # Calculate 20-Day SMA
        df['SMA'] = df['Close'].rolling(window=periods).mean()

        if df['SMA'].dropna().empty:
            continue

        last_close = float(df["Close"].iloc[-1])
        last_sma = float(df["SMA"].iloc[-1])

        # Determine the trend status
        status = "Above SMA" if last_close > last_sma else "Below SMA"
        
        # Calculate deviation percentage for visual context
        deviation_pct = ((last_close - last_sma) / last_sma) * 100

        results.append({
            "symbol": symbol,
            "sma_period": periods,
            "last_close": round(last_close, 2),
            "last_sma": round(last_sma, 2),
            "status": status,
            "deviation_pct": round(deviation_pct, 2),
            "as_of": df.index[-1].strftime("%Y-%m-%d")
        })

    if not results:
        return jsonify({"error": "No valid Moving Average data found"}), 400

    # Sort to show the biggest movers (positive deviation) first
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(by="deviation_pct", ascending=False)

    return jsonify(df_results.to_dict(orient="records"))

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
