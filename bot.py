import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Get all from environment variables
TOKEN = os.getenv("TELEGRAM_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "I'm your Outlook Email Bot.\n\n"
        "Use /connect to link your Outlook account\n"
        "Use /help for more info"
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate Outlook auth link"""
    user_id = update.effective_user.id
    
    if not all([CLIENT_ID, REDIRECT_URI]):
        await update.message.reply_text("❌ Server configuration incomplete")
        return
    
    # Create auth URL
    from urllib.parse import quote
    auth_url = (
        f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={quote(REDIRECT_URI)}"
        f"&scope=Mail.Read%20offline_access"
        f"&state={user_id}"
    )
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [[InlineKeyboardButton("🔗 Connect Outlook", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Click below to connect Outlook account:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Available Commands:\n\n"
        "/start - Welcome message\n"
        "/connect - Link Outlook account\n"
        "/help - Show this message\n\n"
        "First, use /connect to authorize access."
    )

def main():
    """Start the bot"""
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN not set in environment!")
        return
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("connect", connect))
    application.add_handler(CommandHandler("help", help_command))
    
    # Start polling
    logger.info("🚀 Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
