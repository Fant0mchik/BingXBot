import asyncio
from utils import chunked
from symbols import get_filtered_symbols
from test import BingXWS

async def start_all_ws():
    symbols = get_filtered_symbols()

    for group in chunked(symbols, 50):
        ws = BingXWS(group)
        asyncio.create_task(ws.start())

        await asyncio.sleep(0.2)  # анти-флуд