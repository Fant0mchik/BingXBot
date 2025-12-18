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


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

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
        self.prices = deque(maxlen=120)
        self.times = deque(maxlen=120)
        self.volumes = deque(maxlen=120)


        self.candles = None
        self.orderbook = None


        self.last_event_ts = 0
        self.cooldown = 30

    def update_price(self, price):
        self.prices.append(price)
        self.times.append(time.time())
        self.detect_events()

    def update_volume(self, volume):
        self.volumes.append(volume)

    def detect_events(self):
        if len(self.prices) < 30:
            return


        cur = self.prices[-1]
        now = time.time()


        if now - self.last_event_ts < self.cooldown:
            return


        window_prices = list(self.prices)
        window_times = list(self.times)


        low = min(window_prices)
        high = max(window_prices)


        low_idx = window_prices.index(low)
        high_idx = window_prices.index(high)


        delta_up = (cur - low) / low * 100
        delta_down = (cur - high) / high * 100


        duration_up = now - window_times[low_idx]
        duration_down = now - window_times[high_idx]


        speed_up = delta_up / duration_up if duration_up > 0 else 0
        speed_down = abs(delta_down) / duration_down if duration_down > 0 else 0


        if delta_up >= 4 and speed_up >= 0.015:
            logging.warning("Pump detected")
            notify("PUMP", self.details(cur))
            self.last_event_ts = now
            return


        if delta_down <= -4 and speed_down >= 0.015:
            logging.warning("Dump detected")
            notify("DUMP", self.details(cur))
            self.last_event_ts = now
            return


        funding = get_funding_rate(self.symbol)
        vwap = sum(window_prices) / len(window_prices)


        if funding is not None:
            if funding > 0.01 and cur > vwap * 1.03:
                logging.warning("OVERPUMP detected")
                notify("OVERPUMP — SHORT ZONE", self.details(cur, funding))
                self.last_event_ts = now

    def details(self, price, funding=None):
        return {
            "symbol": self.symbol,
            "price": price,
            "volume": sum(self.volumes),
            "candle": self.candles,
            "orderbook": self.orderbook,
            "funding_rate": funding
        }


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
            #logging.info(f"Raw message: {raw}")  
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
        if symbol not in self.analyzers:
            return

        a = self.analyzers[symbol]

        if "lastPrice" in d:
            a.update_price(float(d["lastPrice"]))

        if "k" in d and "v" in d["k"]:
            a.update_volume(float(d["k"]["v"]))
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