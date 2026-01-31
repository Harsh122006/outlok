import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLIENT_ID = os.getenv("MS_CLIENT_ID")
REDIRECT_URI = os.getenv("REDIRECT_URI")
TENANT = os.getenv("MS_TENANT_ID", "common")

AUTH_URL = (
    f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize"
    f"?client_id={CLIENT_ID}"
    f"&response_type=code"
    f"&redirect_uri={REDIRECT_URI}"
    f"&response_mode=query"
    f"&scope=offline_access Mail.Read"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\nUse /connect to link your Outlook account."
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🔐 Click to connect your Outlook:\n\n{AUTH_URL}"
    )

def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.run_polling()

if __name__ == "__main__":
    run_bot()
