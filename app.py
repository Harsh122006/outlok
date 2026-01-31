import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]  # https://xxxx.up.railway.app

app = FastAPI()
telegram_app: Application | None = None


# -------- Telegram handlers --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bot is alive!\n\nSend /start again anytime."
    )


# -------- FastAPI startup --------
@app.on_event("startup")
async def on_startup():
    global telegram_app

    telegram_app = Application.builder().token(TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))

    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    print("✅ Webhook set")


# -------- Telegram webhook --------
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


# -------- Health check --------
@app.get("/")
def health():
    return {"status": "ok"}


# -------- Local run (Railway uses this) --------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
