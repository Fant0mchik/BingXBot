# run.py (updated with nest_asyncio)
import asyncio
import nest_asyncio
from main import application
from ws_manager import start_all_ws
from main import notify
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)
nest_asyncio.apply()
import main
main.notify_loop = asyncio.get_event_loop()

async def main():
    asyncio.create_task(start_all_ws())
    notify("Bot started", None)
    try:  
        await application.run_polling(timeout=90)
    except Exception as e:
        logging.error(f"Error running the polling: {e}")

if __name__ == "__main__":
    asyncio.run(main())