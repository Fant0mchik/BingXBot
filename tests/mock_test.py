# mock_test.py

import json
import time
import gzip
import io
import requests
import websocket
import asyncio
from collections import deque

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
        self.get_time = time.time  # Add for mocking

        self.candles = None
        self.orderbook = None
        self.last_peak = None
        self.last_peak_time = None

    def update_price(self, price):
        self.prices.append(price)
        self.times.append(self.get_time())
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
            test_notify("DUMP", self.details(cur))
            self.reset()

        if delta >= 5 and speed > 0.02:
            test_notify("PUMP", self.details(cur))
            self.reset()

        if 8 <= delta <= 30 and speed > 0.03:
            self.last_peak = cur
            self.last_peak_time = self.get_time()

        if self.last_peak and self.get_time() - self.last_peak_time >= 15:
            funding = get_funding_rate(self.symbol)
            vwap = sum(self.prices) / len(self.prices)

            if funding and funding > 0.01 and cur > vwap * 1.03:
                test_notify("OVERPUMP — SHORT ZONE", self.details(cur,funding))
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

    def on_open(self, ws):
        i = 1
        for s in self.symbols:
            for ch in (
                f"{s}@lastPrice",
                f"{s}@kline_1m",
                f"{s}@depth5@500ms",
                f"{s}@bookTicker"
            ):
                ws.send(json.dumps({
                    "id": str(i),
                    "reqType": "sub",
                    "dataType": ch
                }))
                i += 1

    def on_message(self, ws, message):
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(message)).read().decode()
        except:
            return  # Handle decompression errors gracefully

        if raw == "Ping":
            ws.send("Pong")
            return
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return  # Handle invalid JSON

        data = msg.get("data")

        if not data:
            return
        
        if isinstance(data, list):
            for item in data:
                self.handle_data(item)
        elif isinstance(data, dict):
            self.handle_data(data)

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
        ws = websocket.WebSocketApp(
            URL,
            on_open=self.on_open,
            on_message=self.on_message,
        )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, ws.run_forever)

# Mock notify for testing (replace real notify with print)
def test_notify(event, details=None):
    print(f"TEST NOTIFY: Event = {event}, Details = {details}")

# Mock get_funding_rate for testing
def test_get_funding_rate(symbol):
    return 0.02  # Positive funding to trigger overpump

# Test DUMP (price drops by ~20%)
print("--- Testing DUMP ---")
analyzer_dump = MarketAnalyzer("TEST-USDT")
current_time = 0.0
analyzer_dump.get_time = lambda: current_time  # Mock time
initial_price = 100.0
for i in range(30):  # More than 20 to ensure
    price = initial_price * (1 - (i+1)*0.01)
    analyzer_dump.update_price(price)
    current_time += 0.1  # Adjust duration for speed

# Test PUMP (price rises by ~15%, speed >0.02)
print("--- Testing PUMP ---")
analyzer_pump = MarketAnalyzer("TEST-USDT")
current_time = 0.0
analyzer_pump.get_time = lambda: current_time
initial_price = 100.0
for i in range(30):
    price = initial_price * (1 + (i+1)*0.005)
    analyzer_pump.update_price(price)
    current_time += 0.05  # Adjust to make speed >0.02

# Test OVERPUMP (price rises by ~30%, then simulate long wait with low speed, funding >0.01, cur > vwap*1.03)
print("--- Testing OVERPUMP ---")
analyzer_overpump = MarketAnalyzer("TEST-USDT")
current_time = 0.0
analyzer_overpump.get_time = lambda: current_time
analyzer_overpump.get_funding_rate = test_get_funding_rate  # Mock funding
initial_price = 100.0
for i in range(30):
    price = initial_price * (1 + (i+1)*0.01)
    analyzer_overpump.update_price(price)
    current_time += 0.05
# Simulate a long wait to make speed low, but time since last_peak >=15
current_time += 700  # Large enough to make speed <0.03
# Update with a price that is still high but delta in range, speed low
analyzer_overpump.update_price(120.0)  # Choose 120 > vwap*1.03 (~119)

print("Tests completed")