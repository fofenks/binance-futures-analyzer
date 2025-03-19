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

# Tek günlük analiz endpoint'i
@app.route('/analyze')
async def analyze():
    date_str = request.args.get('date', '2025-03-27')
    threshold = request.args.get('threshold', '15')
    mode = request.args.get('mode', 'open/close')  # Varsayılan "open/close"
    try:
        selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        threshold = float(threshold)
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
        if market.get('active') and market.get('quote') == "USDT" and 
           market.get('swap', False) and market.get('linear', False)
    ]

    async def fetch_symbol_data(symbol, day_ts):
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe='1d', since=day_ts, limit=1)
            if ohlcv and len(ohlcv) > 0:
                ts, open_price, high_price, low_price, close_price, volume = ohlcv[0]
                if ts - day_ts > 86400000:
                    return None
                if mode == 'low/high':
                    if close_price > open_price:
                        daily_change = ((low_price - high_price) / low_price) * 100
                    elif close_price < open_price:
                        daily_change = -((high_price - low_price) / high_price) * 100
                    else:
                        daily_change = 0
                else:  # open/close modunda hesaplama
                    daily_change = ((close_price - open_price) / open_price) * 100
                return (symbol, daily_change)
        except Exception as e:
            print(f"{symbol} için veri çekilirken hata ({datetime.datetime.fromtimestamp(day_ts/1000).strftime('%Y-%m-%d')}): {e}")
        return None

    tasks = [fetch_symbol_data(symbol, since_timestamp) for symbol in usdt_perpetual_symbols]
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
        "mode": mode,
        "increases": increases_sorted,
        "decreases": decreases_sorted,
        "increases_count": len(increases_sorted),
        "decreases_count": len(decreases_sorted)
    }
    return jsonify(result)


# Yeni endpoint: Belirtilen tarih aralığında her gün için analiz yapar
@app.route('/analyze_range')
async def analyze_range():
    start_date_str = request.args.get('start_date', '2025-03-27')
    end_date_str = request.args.get('end_date', '2025-03-27')
    threshold = request.args.get('threshold', '15')
    mode = request.args.get('mode', 'open/close')
    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
        threshold = float(threshold)
    except ValueError:
        return jsonify({"error": "Geçersiz tarih formatı veya yüzdelik değer. YYYY-MM-DD formatında tarih girin."}), 400

    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    markets = await exchange.fetch_markets()
    valid_symbols = [
        market['symbol'] for market in markets
        if market.get('active') and market.get('quote') == "USDT" and 
           market.get('swap', False) and market.get('linear', False)
    ]

    semaphore = asyncio.Semaphore(10)

    async def fetch_symbol_data_for_day(symbol, day_ts):
        async with semaphore:
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe='1d', since=day_ts, limit=1)
                if ohlcv and len(ohlcv) > 0:
                    ts, open_price, high_price, low_price, close_price, volume = ohlcv[0]
                    if ts - day_ts > 86400000:
                        return None
                    if mode == 'low/high':
                        if close_price > open_price:
                            daily_change = -((low_price - high_price) / low_price) * 100
                        elif close_price < open_price:
                            daily_change = -((high_price - low_price) / high_price) * 100
                        else:
                            daily_change = 0
                    else:
                        daily_change = ((close_price - open_price) / open_price) * 100
                    return (symbol, daily_change)
            except Exception as e:
                print(f"{symbol} için {datetime.datetime.fromtimestamp(day_ts/1000).strftime('%Y-%m-%d')} tarihinde veri çekilirken hata: {e}")
            return None

    daily_results = []
    current_date = start_date
    while current_date <= end_date:
        day_ts = int(current_date.timestamp() * 1000)
        tasks = [fetch_symbol_data_for_day(symbol, day_ts) for symbol in valid_symbols]
        results = await asyncio.gather(*tasks)
        symbol_changes = [res for res in results if res is not None]

        increases = [(symbol, change) for symbol, change in symbol_changes if change >= threshold]
        decreases = [(symbol, change) for symbol, change in symbol_changes if change <= -threshold]

        increases_sorted = sorted(increases, key=lambda x: x[1], reverse=True)
        decreases_sorted = sorted(decreases, key=lambda x: x[1])

        daily_results.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "threshold": threshold,
            "mode": mode,
            "increases": increases_sorted,
            "decreases": decreases_sorted,
            "increases_count": len(increases_sorted),
            "decreases_count": len(decreases_sorted)
        })
        current_date += datetime.timedelta(days=1)

    await exchange.close()
    return jsonify({"daily_results": daily_results})

if __name__ == '__main__':
    app.run(debug=True)
