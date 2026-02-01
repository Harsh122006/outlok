import os
import aiohttp
from datetime import datetime, timeddelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Configuration
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")

# Storage
user_tokens = {}

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Outlook Email Bot!\n\n"
        "Commands:\n"
        "/connect - Link Outlook\n"
        "/inbox - Read emails\n"
        "/help - Show help"
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # FIX: Ensure WEBHOOK_URL is properly set
    if not WEBHOOK_URL:
        await update.message.reply_text("❌ Server URL not configured")
        return
    
    # FIX: Proper redirect URI with https
    redirect_uri = f"https://{WEBHOOK_URL.split('//')[-1]}/auth/callback"
    
    # FIX: Properly encoded URL
    auth_url = (
        f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&scope=Mail.Read%20offline_access"
        f"&state={user_id}"
    )
    
    keyboard = [[InlineKeyboardButton("🔗 Connect Outlook", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Click to connect Outlook:",
        reply_markup=reply_markup
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_tokens:
        await update.message.reply_text("❌ Please use /connect first")
        return
    
    tokens = user_tokens[user_id]
    
    # Check if token is expired
    if datetime.now() > tokens.get('expires_at', datetime.now()):
        await update.message.reply_text("❌ Session expired. Use /connect again")
        return
    
    await update.message.reply_text("✅ Fetching emails...")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Help:\n"
        "/connect - Link Outlook account\n"
        "/inbox - Read emails\n"
        "/help - This message"
    )

# ==================== TOKEN MANAGEMENT ====================

async def exchange_code_for_token(code: str):
    """Exchange auth code for tokens"""
    if not WEBHOOK_URL:
        return None
    
    redirect_uri = f"https://{WEBHOOK_URL.split('//')[-1]}/auth/callback"
    
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "scope": "Mail.Read offline_access"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data) as response:
                if response.status == 200:
                    tokens = await response.json()
                    tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
                    return tokens
    except Exception as e:
        print(f"Token exchange error: {e}")
    return None

def handle_auth_callback(code: str, state: str):
    """Store tokens after OAuth"""
    import asyncio
    
    try:
        user_id = int(state)
        tokens = asyncio.run(exchange_code_for_token(code))
        
        if tokens:
            user_tokens[user_id] = tokens
            return user_id, True
    except Exception as e:
        print(f"Auth callback error: {e}")
    return None, False

# ==================== CREATE APPLICATION ====================

def create_application():
    """Create Telegram bot application"""
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
    
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("connect", connect))
    application.add_handler(CommandHandler("inbox", inbox))
    application.add_handler(CommandHandler("help", help_command))
    
    return application
