
import logging
import os
import json
from dotenv import load_dotenv
from telegram import Update
import asyncio
import telegram
from telegram.request import HTTPXRequest
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from render_chart import render_candles

load_dotenv()
TOKEN = os.getenv("TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

NOTIFY_FILE = "notify_chats.json"

def load_notify_chats():
    if not os.path.exists(NOTIFY_FILE):
        return []
    with open(NOTIFY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_notify_chats(chats):
    with open(NOTIFY_FILE, "w", encoding="utf-8") as f:
        json.dump(chats, f, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #logging.info("Received /start")
    await update.message.reply_text("/notifyhere - Send messages about BingX USDT 0.0001-1$ Coins events.")
    #logging.info("Sent /start response")

def notify(event, details=None):
    lines = []

    # Заголовок події
    lines.append(f"{'🟡' if event=='PUMP' else '🔵' if event=='DUMP' else '🔴'} <b>{event}</b>\n")
    path = None
    if details:
        # Символ
        if "symbol" in details:
            lines.append(f"🪙 <b>Symbol:</b> <code>{details['symbol']}</code>\n")

        # Ціна
        if "price" in details:
            lines.append(f"💰 <b>Price:</b> <code>{details['price']}</code>\n")

        if "percent" in details:
            lines.append(f"📈 <b>Change:</b> <code>{details['percent']}%</code>\n")

        # Обʼєм
        if "volume" in details and details["volume"] is not None:
            lines.append(f"📊 <b>Volume:</b> <code>{details['volume']}</code>\n")

        # Funding rate
        if "funding_rate" in details and details["funding_rate"] is not None:
            lines.append(f"⚡ <b>Funding rate:</b> <code>{details['funding_rate']}</code>\n")

        # Свічка

        candles = list(details.get("candles"))
        symbol = details.get("symbol")

        if isinstance(candles, list) and symbol:
            path = f"images/{symbol}_chart.png"
            for filename in os.listdir("images/"):
                if os.path.isfile(filename):
                    try:
                        os.remove(f"images/{filename}")
                    except Exception as e:
                        logging.error(f"Error deleting file {filename}: {e}")

            render_candles(symbol, candles, path)

        # candle = details.get("candle")
        # if isinstance(candle, dict):
        #     lines.append("🕯 <b>Candle (1m):</b>")
        #     for key in ("open", "high", "low", "close", "volume"):
        #         if key in candle:
        #             lines.append(f"   > {key}: <code>{candle[key]}</code>")
        #     lines.append("\n")

        # Стакан
        orderbook = details.get("orderbook")
        if isinstance(orderbook, dict):
            lines.append("📘 <b>Orderbook (top):</b>")

            bids = orderbook.get("bids", [])[:3]
            asks = orderbook.get("asks", [])[:3]

            if bids:
                lines.append("  🟢 <b>Bids:</b>")
                for price, qty in bids:
                    lines.append(f"    <code>{price} × {qty}</code>")

            if asks:
                lines.append("  🔴 <b>Asks:</b>")
                for price, qty in asks:
                    lines.append(f"    <code>{price} × {qty}</code>")
            lines.append("\n")

    message_text = "\n".join(lines)

    for chat_id in load_notify_chats():
        asyncio.run_coroutine_threadsafe(
            application.bot.send_photo(
                chat_id,
                photo=open(path, 'rb') if os.path.exists(path) else None,
                caption=message_text,
                parse_mode="HTML"          
            ),
            notify_loop  
        ) if path else asyncio.run_coroutine_threadsafe(
            application.bot.send_message(
                chat_id,
                text=message_text,
                parse_mode="HTML"
            ),
            notify_loop  
        )

async def notifyhere(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chats = load_notify_chats()

    if chat_id in chats:
        chats.remove(chat_id)
        save_notify_chats(chats)
        await update.message.reply_text("❌ Notifications disabled for this chat")
    else:
        chats.append(chat_id)
        save_notify_chats(chats)
        await update.message.reply_text("✅ Notifications enabled for this chat")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f"Exception occurred: {context.error}")
    if isinstance(context.error, telegram.error.TimedOut):
        logging.info("Retrying on TimedOut...")

request = HTTPXRequest(
    connection_pool_size=10,
    read_timeout=90.0,
    write_timeout=90.0,
    connect_timeout=90.0,
    pool_timeout=10.0,
    http_version="1.1"
)

application = ApplicationBuilder().token(TOKEN).request(request).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("notifyhere", notifyhere))
application.add_error_handler(error_handler) 

notify_loop = asyncio.get_event_loop()