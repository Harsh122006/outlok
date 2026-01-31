import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ENV VARIABLES
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://xxxx.up.railway.app

app = FastAPI()

telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# ---------------- COMMANDS ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Outlook Mail Bot!\n\n"
        "Use /connect to link your Outlook account."
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 Outlook connection coming next.\n"
        "OAuth flow will be triggered here."
    )

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("connect", connect))

# ---------------- STARTUP ---------------- #

@app.on_event("startup")
async def startup():
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    print("✅ Telegram webhook registered")

# ---------------- WEBHOOK ---------------- #

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

# ---------------- HEALTH ---------------- #

@app.get("/")
def health():
    return {"status": "ok"}
