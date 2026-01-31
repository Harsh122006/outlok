import os
from telegram.ext import Application, CommandHandler

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update, context):
    await update.message.reply_text(
        "Use /connect to link Outlook account"
    )

async def connect(update, context):
    auth_url = (
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        "?client_id=" + os.getenv("MS_CLIENT_ID") +
        "&response_type=code"
        "&redirect_uri=" + os.getenv("REDIRECT_URI") +
        "&response_mode=query"
        "&scope=offline_access%20Mail.Read"
    )
    await update.message.reply_text(auth_url)

async def start_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    await app.initialize()
    await app.start()
    await app.bot.initialize()
    print("🤖 Bot polling")
    await app.stop()  # keeps task alive
