import sys
import asyncio
import datetime
from flask import Flask, render_template, jsonify, request

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import ccxt.async_support as ccxt
async def main():
    # Binance Futures API'ye bağlan (defaultType: future)
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    # Tüm piyasaları çek
    markets = await exchange.fetch_markets()

    # Sadece aktif, USDT bazlı ve perpetual (swap=True ve linear=True) piyasaları filtrele
    usdt_perpetuals = [
        market for market in markets
        if market.get('active') 
           and market.get('quote') == "USDT" 
           and market.get('swap', False) 
           and market.get('linear', False)
    ]

    # Toplam sayıyı terminale yazdır
    print(f"Total count of USDT perpetual futures: {len(usdt_perpetuals)}")

    # Bağlantıyı kapat
    await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
