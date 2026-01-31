import os
import asyncio
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN is missing")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is running!")

async def start_bot():
    print("🤖 Initializing Telegram bot...")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    await application.initialize()
    await application.start()

    print("🤖 Telegram polling started")

    # 🚨 REQUIRED: keep process alive forever
    await asyncio.Event().wait()
