import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\nUse /connect to link your Outlook account."
    )


async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_id = os.environ.get("MS_CLIENT_ID")
    redirect_uri = os.environ.get("REDIRECT_URI")

    auth_url = (
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        f"?client_id={client_id}"
        "&response_type=code"
        f"&redirect_uri={redirect_uri}"
        "&response_mode=query"
        "&scope=offline_access Mail.Read"
    )

    await update.message.reply_text(
        f"🔐 Click to connect your Outlook:\n{auth_url}"
    )


async def run_telegram_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))

    print("✅ Telegram bot started")
    await app.run_polling()
