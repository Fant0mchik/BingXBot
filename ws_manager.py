import asyncio
import logging
from utils import chunked
from symbols import get_filtered_symbols
from test import BingXWS

async def start_all_ws():
    symbols = get_filtered_symbols()
    #symbols = ["WIF-USDT"]
    
    if not symbols:
        logging.error("No symbols retrieved from API. Cannot start WebSocket connections.")
        return

    logging.info(f"Starting WebSocket connections for {len(symbols)} symbols")

    for group in chunked(symbols, 40):
        ws = BingXWS(group)
        asyncio.create_task(ws.start())

        await asyncio.sleep(0.2)  # анти-флуд