import sys
import asyncio
import datetime
from flask import Flask, render_template, jsonify, request

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import ccxt.async_support as ccxt

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze')
async def analyze():
    date_str = request.args.get('date', '2025-03-01')
    threshold = request.args.get('threshold', '15')  # Varsayılan %15
    try:
        selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        threshold = float(threshold)  # Gelen değeri sayıya çeviriyoruz
    except ValueError:
        return jsonify({"error": "Geçersiz giriş. Lütfen doğru tarih ve yüzdelik değer girin."}), 400

    since_timestamp = int(selected_date.timestamp() * 1000)

    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    markets = await exchange.fetch_markets()
    usdt_perpetual_symbols = [
        market['symbol'] for market in markets
        if market['active'] and market['quote'] == "USDT" and market.get('swap', False)
    ]

    async def fetch_symbol_data(symbol):
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe='1d', since=since_timestamp, limit=1)
            if ohlcv and len(ohlcv) > 0:
                ts, open_price, high_price, low_price, close_price, volume = ohlcv[0]
                daily_change = ((close_price - open_price) / open_price) * 100
                return (symbol, daily_change)
        except Exception as e:
            print(f"{symbol} için veri çekilirken hata oluştu: {e}")
        return None

    tasks = [fetch_symbol_data(symbol) for symbol in usdt_perpetual_symbols]
    results = await asyncio.gather(*tasks)
    symbol_changes = [res for res in results if res is not None]

    increases = [(symbol, change) for symbol, change in symbol_changes if change >= threshold]
    decreases = [(symbol, change) for symbol, change in symbol_changes if change <= -threshold]

    increases_sorted = sorted(increases, key=lambda x: x[1], reverse=True)
    decreases_sorted = sorted(decreases, key=lambda x: x[1])

    await exchange.close()

    result = {
        "date": date_str,
        "threshold": threshold,
        "increases": increases_sorted,
        "decreases": decreases_sorted,
        "increases_count": len(increases_sorted),
        "decreases_count": len(decreases_sorted)
    }
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)
