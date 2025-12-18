import json
import time
import gzip
import io
import requests
import websockets
import asyncio
from collections import deque
from main import notify  
import logging  


logging.basicConfig(level=logging.INFO)

URL = "wss://open-api-swap.bingx.com/swap-market"
FUNDING_URL = "https://open-api.bingx.com/openApi/swap/v2/quote/fundingRate"

# ---------------- FUNDING ---------------- #

funding_cache = {}
funding_ts = {}

def get_funding_rate(symbol):
    now = time.time()
    if symbol in funding_cache and now - funding_ts[symbol] < 60:
        return funding_cache[symbol]

    try:
        r = requests.get(FUNDING_URL, params={"symbol": symbol}, timeout=3)
        rate = float(r.json()["data"]["fundingRate"])
        funding_cache[symbol] = rate
        funding_ts[symbol] = now
        return rate
    except:
        return None

# ---------------- ANALYZER ---------------- #

class MarketAnalyzer:
    def __init__(self, symbol):
        self.symbol = symbol
        self.prices = deque(maxlen=300)
        self.volumes = deque(maxlen=300)
        self.times = deque(maxlen=300)

        self.candles = None
        self.orderbook = None
        self.last_peak = None
        self.last_peak_time = None

    def update_price(self, price):
        self.prices.append(price)
        self.times.append(time.time())
        self.detect_events()

    def update_volume(self, volume):
        self.volumes.append(volume)

    def detect_events(self):
        if len(self.prices) < 20:
            return

        start = self.prices[0]
        cur = self.prices[-1]
        delta = (cur - start) / start * 100
        duration = self.times[-1] - self.times[0]
        speed = abs(delta) / duration if duration else 0

        if -30 <= delta <= -10:
            notify("DUMP", self.details(cur))
            self.reset()

        if delta >= 5 and speed > 0.02:
            notify("PUMP", self.details(cur))
            self.reset()

        if 8 <= delta <= 30 and speed > 0.03:
            self.last_peak = cur
            self.last_peak_time = time.time()

        if self.last_peak and time.time() - self.last_peak_time >= 15:
            funding = get_funding_rate(self.symbol)
            vwap = sum(self.prices) / len(self.prices)

            if funding and funding > 0.01 and cur > vwap * 1.03:
                notify("OVERPUMP — SHORT ZONE", self.details(cur,funding))
                self.reset()

    def details(self, price, funding=None):
        return {
            "symbol": self.symbol,
            "price": price,
            "volume": sum(self.volumes),
            "candle": self.candles,
            "orderbook": self.orderbook,
            "funding_rate": funding
        }

    def reset(self):
        self.prices.clear()
        self.times.clear()
        self.last_peak = None
        self.last_peak_time = None

# ---------------- WS ---------------- #

class BingXWS:
    def __init__(self, symbols):
        self.symbols = symbols
        self.analyzers = {s: MarketAnalyzer(s) for s in symbols}

    async def subscribe(self, ws):
        logging.info(f"WebSocket connected for symbols: {self.symbols}")
        i = 1
        for s in self.symbols:
            for ch in (
                f"{s}@lastPrice",
                f"{s}@kline_1m",
                f"{s}@depth5@500ms",
                f"{s}@bookTicker"
            ):
                await ws.send(json.dumps({
                    "id": str(i),
                    "reqType": "sub",
                    "dataType": ch
                }))
                i += 1

    async def process_message(self, message):
        try:
            raw = gzip.decompress(message).decode()
            #logging.debug(f"Raw message: {raw}")  # Debug raw
        except Exception as e:
            logging.error(f"Decompression error: {e}")
            return

        if raw == "Ping":
            logging.info("Received Ping, sending Pong")
            return "Pong"
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}")
            return None

        data = msg.get("data")

        if not data:
            return None

        if isinstance(data, list):
            for item in data:
                self.handle_data(item)
        elif isinstance(data, dict):
            self.handle_data(data)

        return None  # No response needed

    def handle_data(self, d):
        symbol = d.get("symbol")
        if not symbol or symbol not in self.analyzers:
            return

        a = self.analyzers[symbol]

        if "lastPrice" in d:
            a.update_price(float(d["lastPrice"]))

        if "v" in d:
            a.update_volume(float(d["v"]))

        if "k" in d:
            a.candles = d

        if "bids" in d:
            a.orderbook = d

    async def start(self):
        while True:
            try:
                async with websockets.connect(URL) as ws:
                    await self.subscribe(ws)
                    async for message in ws:
                        response = await self.process_message(message)
                        if response:
                            await ws.send(response)
            except websockets.exceptions.ConnectionClosed as e:
                logging.info(f"Connection closed: {e}")
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
            logging.info("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)