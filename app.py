import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# -------- ENV --------
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]  # https://xxx.up.railway.app

# -------- APP --------
app = FastAPI()
tg_app = Application.builder().token(BOT_TOKEN).build()

# -------- BOT COMMANDS --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bot is alive.\nUse /connect next."
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 OAuth will be added here."
    )

tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("connect", connect))

# -------- STARTUP --------
@app.on_event("startup")
async def startup():
    await tg_app.initialize()
    await tg_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    print("✅ Webhook set")

# -------- WEBHOOK --------
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}

# -------- HEALTH --------
@app.get("/")
def health():
    return {"status": "ok"}
