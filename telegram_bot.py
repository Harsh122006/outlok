import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ======================
# Environment Variables
# ======================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
REDIRECT_URI = os.getenv("REDIRECT_URI")

if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

if not MS_CLIENT_ID or not REDIRECT_URI:
    raise RuntimeError("Missing Microsoft OAuth environment variables")

# ======================
# Microsoft OAuth URL
# ======================
AUTH_URL = (
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
    "?client_id={client_id}"
    "&response_type=code"
    "&redirect_uri={redirect_uri}"
    "&response_mode=query"
    "&scope=offline_access Mail.Read"
)

# ======================
# Telegram Handlers
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to Outlook Mail Bot*\n\n"
        "I can notify you about new Outlook emails.\n\n"
        "Use /connect to link your Outlook account.",
        parse_mode="Markdown",
    )


async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    oauth_url = AUTH_URL.format(
        client_id=MS_CLIENT_ID,
        redirect_uri=REDIRECT_URI,
    )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔐 Connect Outlook", url=oauth_url)]]
    )

    await update.message.reply_text(
        "🔗 *Click below to connect your Outlook account*",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – Welcome message\n"
        "/connect – Connect Outlook account\n"
        "/help – Show this help"
    )


# ======================
# App Factory
# ======================
def create_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("help", help_cmd))

    return app
