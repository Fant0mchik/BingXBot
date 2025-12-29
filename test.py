import json
import time
import gzip
import aiohttp
import websockets
import asyncio
import threading
from collections import deque
from main import notify  
import logging  


DEBUG = True
URL = "wss://open-api-swap.bingx.com/swap-market"
FUNDING_URL = "https://open-api.bingx.com/openApi/swap/v2/quote/fundingRate"

# ---------------- FUNDING ---------------- #

funding_cache = {}
funding_ts = {}
_funding_session = None
_funding_lock = threading.Lock()

async def get_global_funding_session():
    global _funding_session
    with _funding_lock:
        if _funding_session is None or _funding_session.closed:
            _funding_session = aiohttp.ClientSession()
    return _funding_session

async def close_global_funding_session():
    global _funding_session
    with _funding_lock:
        if _funding_session and not _funding_session.closed:
            await _funding_session.close()
            _funding_session = None

async def get_funding_rate_async(symbol):
    now = time.time()
    if symbol in funding_cache and now - funding_ts[symbol] < 60:
        return funding_cache[symbol]

    try:
        session = await get_global_funding_session()
        async with session.get(FUNDING_URL, params={"symbol": symbol}, timeout=aiohttp.ClientTimeout(total=2)) as r:
            if r.status == 200:
                data = await r.json()
                rate = float(data["data"]["fundingRate"])
                funding_cache[symbol] = rate
                funding_ts[symbol] = now
                return rate
    except Exception as e:
        logging.debug(f"Failed to get funding rate for {symbol}: {e}")
    return None

# ---------------- ANALYZER ---------------- #

class MarketAnalyzer:
    def __init__(self, symbol):
        self.symbol = symbol
        self.prices = deque(maxlen=240)
        self.times = deque(maxlen=240)
        self.volumes = deque(maxlen=240)


        self.candles = deque(maxlen=240)
        self.orderbook = None


        self.last_event_ts = 0
        self.cooldown = 30
        self.last_debug_ts = 0
        self._cached_vwap = None
        self._cached_volume_sum = None

        self.last_pump_price = None
        self.last_dump_price = None
        self.last_pump_time = 0
        self.last_dump_time = 0

        self.min_price_change_for_repeat = 0.05  # 5%

        self.price_reset_timeout = 3600  


    def update_price(self, price):
        self.prices.append(price)
        self.times.append(time.time())
        self._cached_vwap = None



    def update_volume(self, volume):
        self.volumes.append(volume)
        self._cached_volume_sum = None


    def detect_events(self):
        if len(self.prices) < 30:
            return

        cur = self.prices[-1]
        now = time.time()


        # -------- DEBUG lastPrice flow --------
        if now - self.last_debug_ts > 60:
            logging.info(
                f"[DEBUG] {self.symbol} lastPrice={cur} ticks={len(self.prices)}"
                )
            self.last_debug_ts = now
                


        if now - self.last_event_ts < self.cooldown:
            return


        indices = [i for i, t in enumerate(self.times) if now - t <= 300]
        if len(indices) < 2:
            return

        first_idx = indices[0]
        low = high = self.prices[first_idx]
        low_idx = high_idx = first_idx

        for i in indices:
            price = self.prices[i]
            if price < low:
                low = price
                low_idx = i
            if price > high:
                high = price
                high_idx = i

        volatility = (high - low) / low if low > 0 else 0
        if volatility < 0.02:  
            return

        delta_up = (cur - low) / low * 100
        delta_down = (cur - high) / high * 100

        duration_up = now - self.times[low_idx]
        duration_down = now - self.times[high_idx]


        speed_up = delta_up / duration_up if duration_up > 0 else 0
        speed_down = abs(delta_down) / duration_down if duration_down > 0 else 0



        # -------- DEBUG thresholds --------
        if now - self.last_debug_ts > 5:
            logging.info(
                f"[DEBUG] {self.symbol} Δup={delta_up:.2f}% v_up={speed_up:.4f} Δdown={delta_down:.2f}% v_down={speed_down:.4f}"
                )
                

        if self.last_pump_time > 0 and now - self.last_pump_time > self.price_reset_timeout:
            self.last_pump_price = None
            self.last_pump_time = 0
        
        if self.last_dump_time > 0 and now - self.last_dump_time > self.price_reset_timeout:
            self.last_dump_price = None
            self.last_dump_time = 0

        if delta_up >= 5 and delta_up <= 30 and duration_up >= 5 and duration_up <= 300:      
            should_notify_pump = False
            
            if self.last_pump_price is None:
                should_notify_pump = True
            else:
 
                price_change_from_last = abs(cur - self.last_pump_price) / self.last_pump_price
                if price_change_from_last >= self.min_price_change_for_repeat:
                    should_notify_pump = True
            
            if should_notify_pump:
                logging.warning(f"Pump detected on {self.symbol}: {delta_up:.2f}% за {duration_up:.1f}с (ціна: {cur})")
                notify("PUMP", self.details(cur,f"{delta_up:.2f}"))
                self.last_event_ts = now
                self.last_pump_price = cur
                self.last_pump_time = now
                return



        if delta_down <= -5 and delta_down >= -30 and duration_down >= 5 and duration_down <= 300:
            should_notify_dump = False
            
            if self.last_dump_price is None:

                should_notify_dump = True
            else:
                price_change_from_last = abs(cur - self.last_dump_price) / self.last_dump_price
                if price_change_from_last >= self.min_price_change_for_repeat:
                    should_notify_dump = True
            
            if should_notify_dump:
                logging.warning(f"Dump detected on {self.symbol}: {abs(delta_down):.2f}% за {duration_down:.1f}с (ціна: {cur})")
                notify("DUMP", self.details(cur, f"{abs(delta_down):.2f}"))
                self.last_event_ts = now
                self.last_dump_price = cur
                self.last_dump_time = now
                return


        vwap = sum(self.prices) / len(self.prices) if self.prices else cur
        
        funding = funding_cache.get(self.symbol) if self.symbol in funding_cache else None


        if funding is not None and funding > 0.01 and cur > vwap * 1.03:
            logging.warning(f"OVERPUMP detected on {self.symbol}")
            notify("OVERPUMP — SHORT ZONE", self.details(cur, funding))
            self.last_event_ts = now

    def details(self, price, prcent,funding=None):
        if self._cached_volume_sum is None:
            self._cached_volume_sum = sum(self.volumes)
        return {
            "symbol": self.symbol,
            "price": price,
            "volume": self._cached_volume_sum,
            "candles": self.candles,
            "orderbook": self.orderbook,
            "funding_rate": funding,
            "percent": prcent
        }



# ---------------- WS ---------------- #

class BingXWS:
    def __init__(self, symbols, num_workers=3):
        self.symbols = symbols
        self.analyzers = {s: MarketAnalyzer(s) for s in symbols}
        self.detect_queue = asyncio.Queue(maxsize=len(symbols) * 2)
        self.last_detect = {}
        self.detect_interval = 0.5  # 500ms
        self.pending_symbols = set()
        self._detect_tasks = []
        self.num_workers = num_workers
        self.perf_stats = {
            'total_processed': 0,
            'total_time': 0.0,
            'max_time': 0.0,
            'min_time': float('inf'),
            'last_report_time': time.monotonic(),
            'times': [],
            'lock': asyncio.Lock()  
        }

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
            #logging.info("Received Ping, sending Pong")
            return "Pong"
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}")
            return None

        data = msg.get("data")
        dataType = msg.get("dataType", "")
        if not data:
            return None

        if isinstance(data, list):
            for item in data:
                self.handle_data(item, dataType, msg.get("s"))
        elif isinstance(data, dict):
            self.handle_data(data, dataType, msg.get("s"))

        return None  

    def handle_data(self, d, dataType="", symbol_from_msg=None):
        symbol = d.get("s") or symbol_from_msg
        
        if not symbol and dataType:
            # dataType має формат "SYMBOL@channel", наприклад "WIF-USDT@lastPrice"
            parts = dataType.split("@")
            if parts:
                symbol = parts[0]
        
        if not symbol or symbol not in self.analyzers:
            return

        a = self.analyzers[symbol]

        def _queue_symbol_if_needed(sym):
            now = time.monotonic()
            if sym in self.last_detect and now - self.last_detect[sym] < self.detect_interval:
                return
            if sym in self.pending_symbols:
                return
            try:
                self.detect_queue.put_nowait(sym)
                self.pending_symbols.add(sym)
            except asyncio.QueueFull:
                pass  

        # Обробка @lastPrice: має поле "c" (latest transaction price)
        if "c" in d and "e" in d and d.get("e") == "lastPriceUpdate":
            a.update_price(float(d["c"]))
            _queue_symbol_if_needed(symbol)

        # Обробка @kline_1m: має поля c, o, h, l, v, T
        if "v" in d and "T" in d:
            # Це kline дані
            if "c" in d:
                a.update_price(float(d["c"]))
            if "v" in d:
                a.update_volume(float(d["v"]))
            
            new_candle = {
                "time": d.get("T", 0),
                "open": float(d.get("o", 0)),
                "high": float(d.get("h", 0)),
                "low": float(d.get("l", 0)),
                "close": float(d.get("c", 0)),
                "volume": float(d.get("v", 0))
            }
            
            if a.candles and a.candles[-1]["time"] == new_candle["time"]:
                a.candles[-1] = new_candle
            else:
                a.candles.append(new_candle)
            
            _queue_symbol_if_needed(symbol)

        # Обробка @bookTicker: має поля b, B, a, A
        # Використовуємо best ask price (a) або best bid price (b) як ціну
        if "e" in d and d.get("e") == "bookTicker":
            if "a" in d:
                a.update_price(float(d["a"]))
            elif "b" in d:
                a.update_price(float(d["b"]))
            _queue_symbol_if_needed(symbol)

        # Обробка @depth5@500ms: має поля bids та asks
        if "bids" in d and "asks" in d:
            a.orderbook = d


    async def _funding_rate_updater(self):
        while True:
            try:
                now = time.time()
                symbols_to_update = [
                    s for s in self.symbols 
                    if s not in funding_cache or now - funding_ts.get(s, 0) >= 60
                ]
                

                for i in range(0, len(symbols_to_update), 10):
                    batch = symbols_to_update[i:i+10]
                    tasks = [get_funding_rate_async(s) for s in batch]
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                await asyncio.sleep(30)
            except Exception as e:
                logging.error(f"Error in funding_rate_updater: {e}")
                await asyncio.sleep(5)
    
    async def _detect_events_worker(self, worker_id):
        while True:
            try:
                symbol = await asyncio.wait_for(self.detect_queue.get(), timeout=1.0)
                
                self.pending_symbols.discard(symbol)
                
                now = time.monotonic()
                if symbol in self.last_detect and now - self.last_detect[symbol] < self.detect_interval:
                    continue
                
                self.last_detect[symbol] = now
                
                if symbol in self.analyzers:
                    start_time = time.perf_counter()
                    self.analyzers[symbol].detect_events()
                    elapsed = time.perf_counter() - start_time
                
                    await self._update_perf_stats(elapsed)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"Error in detect_events_worker {worker_id}: {e} ")
    
    async def _update_perf_stats(self, elapsed_time):
        async with self.perf_stats['lock']:
            stats = self.perf_stats
            stats['total_processed'] += 1
            stats['total_time'] += elapsed_time
            stats['max_time'] = max(stats['max_time'], elapsed_time)
            stats['min_time'] = min(stats['min_time'], elapsed_time)
            
            stats['times'].append(elapsed_time)
            if len(stats['times']) > 100:
                stats['times'].pop(0)
            
            now = time.monotonic()
            if now - stats['last_report_time'] >= 10.0:
                await self._log_perf_stats()
                stats['last_report_time'] = now
    
    async def _log_perf_stats(self):
        stats = self.perf_stats
        if stats['total_processed'] == 0:
            return
        
        avg_time = stats['total_time'] / stats['total_processed']
        avg_time_ms = avg_time * 1000
        max_time_ms = stats['max_time'] * 1000
        min_time_ms = stats['min_time'] * 1000 if stats['min_time'] != float('inf') else 0
        
        median_ms = 0
        if stats['times']:
            sorted_times = sorted(stats['times'])
            median = sorted_times[len(sorted_times) // 2]
            median_ms = median * 1000
        
        rate = stats['total_processed'] / 10.0  
        
        queue_size = self.detect_queue.qsize()
        pending_count = len(self.pending_symbols)
        
        logging.info(
            f"[PERF] Processed: {stats['total_processed']} symbols | "
            f"Rate: {rate:.1f} sym/s | "
            f"Avg: {avg_time_ms:.3f}ms | "
            f"Median: {median_ms:.3f}ms | "
            f"Min: {min_time_ms:.3f}ms | "
            f"Max: {max_time_ms:.3f}ms | "
            f"Queue: {queue_size} | "
            f"Pending: {pending_count}"
        )
        
        stats['total_processed'] = 0
        stats['total_time'] = 0.0
        stats['max_time'] = 0.0
        stats['min_time'] = float('inf')

    async def start(self):
        self._detect_tasks = [
            asyncio.create_task(self._detect_events_worker(i))
            for i in range(self.num_workers)
        ]
        
        self._funding_task = asyncio.create_task(self._funding_rate_updater())
        
        try:
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
        finally:
            for task in self._detect_tasks:
                task.cancel()
            if self._funding_task:
                self._funding_task.cancel()
            
            await asyncio.gather(*self._detect_tasks, return_exceptions=True)
            if self._funding_task:
                try:
                    await self._funding_task
                except asyncio.CancelledError:
                    pass