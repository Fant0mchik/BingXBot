# run.py (updated with nest_asyncio)
import asyncio
import nest_asyncio
from main import application
from ws_manager import start_all_ws
from main import notify

nest_asyncio.apply()

async def main():
    asyncio.create_task(start_all_ws())
    notify("Bot started", None)  # Вставте тут
    await application.run_polling(timeout=90)

if __name__ == "__main__":
    asyncio.run(main())