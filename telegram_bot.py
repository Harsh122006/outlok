import aiohttp
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from msal import PublicClientApplication
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MSAL
msal_app = PublicClientApplication(
    client_id=config.CLIENT_ID,
    authority="https://login.microsoftonline.com/consumers"
)

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "👋 *Outlook Email Bot*\n\n"
        "Read your Outlook emails in Telegram!\n\n"
        "Commands:\n"
        "/connect - Link Outlook account\n"
        "/inbox - Read emails\n"
        "/unread - Show unread\n"
        "/disconnect - Remove account\n"
        "/help - Show help",
        parse_mode='Markdown'
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate Outlook auth link"""
    user_id = update.effective_user.id
    
    auth_url = msal_app.get_authorization_request_url(
        scopes=["Mail.Read", "offline_access"],
        redirect_uri=config.REDIRECT_URI,
        state=str(user_id)
    )
    
    keyboard = [[InlineKeyboardButton("🔗 Connect Outlook", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Click below to connect Outlook:\n"
        "1. Login with Microsoft\n"
        "2. Grant 'Read email' permission\n"
        "3. Return to Telegram",
        reply_markup=reply_markup
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Read latest emails"""
    user_id = update.effective_user.id
    
    if user_id not in config.user_tokens:
        await update.message.reply_text("❌ Use /connect first")
        return
    
    tokens = config.user_tokens[user_id]
    
    # Check token expiry
    if datetime.now() > tokens['expires_at']:
        new_tokens = await refresh_token(tokens['refresh_token'])
        if new_tokens:
            config.user_tokens[user_id] = new_tokens
            tokens = new_tokens
        else:
            await update.message.reply_text("❌ Session expired. Use /connect again")
            return
    
    # Fetch emails
    emails = await fetch_emails(tokens['access_token'])
    
    if not emails:
        await update.message.reply_text("📭 No emails found")
        return
    
    response = "📧 *Your Emails:*\n\n"
    for i, email in enumerate(emails[:5]):
        sender = email.get('from', {}).get('emailAddress', {})
        subject = email.get('subject', 'No Subject')
        received = email.get('receivedDateTime', '')[:10]
        
        response += f"*{i+1}. {subject}*\n"
        response += f"   👤 {sender.get('name', 'Unknown')}\n"
        response += f"   📅 {received}\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def unread(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show unread emails"""
    user_id = update.effective_user.id
    
    if user_id not in config.user_tokens:
        await update.message.reply_text("❌ Use /connect first")
        return
    
    tokens = config.user_tokens[user_id]
    
    if datetime.now() > tokens['expires_at']:
        new_tokens = await refresh_token(tokens['refresh_token'])
        if new_tokens:
            config.user_tokens[user_id] = new_tokens
            tokens = new_tokens
    
    emails = await fetch_emails(tokens['access_token'], unread_only=True)
    
    if not emails:
        await update.message.reply_text("🎉 No unread emails!")
        return
    
    response = "🔵 *Unread Emails:*\n\n"
    for i, email in enumerate(emails[:5]):
        sender = email.get('from', {}).get('emailAddress', {})
        subject = email.get('subject', 'No Subject')
        
        response += f"*{i+1}. {subject}*\n"
        response += f"   👤 {sender.get('name', 'Unknown')}\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove account"""
    user_id = update.effective_user.id
    
    if user_id in config.user_tokens:
        del config.user_tokens[user_id]
        await update.message.reply_text("✅ Account disconnected")
    else:
        await update.message.reply_text("ℹ️ No account connected")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    await update.message.reply_text(
        "📋 *Help*\n\n"
        "/connect - Link Outlook\n"
        "/inbox - Read emails\n"
        "/unread - Unread emails\n"
        "/disconnect - Remove account\n"
        "/help - This message",
        parse_mode='Markdown'
    )

# ==================== MICROSOFT GRAPH ====================

async def exchange_code_for_token(code: str):
    """Get tokens from auth code"""
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    data = {
        "client_id": config.CLIENT_ID,
        "client_secret": config.CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": config.REDIRECT_URI,
        "scope": "Mail.Read offline_access"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data) as resp:
            if resp.status == 200:
                tokens = await resp.json()
                tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
                return tokens
    return None

async def refresh_token(refresh_token: str):
    """Refresh access token"""
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    data = {
        "client_id": config.CLIENT_ID,
        "client_secret": config.CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "Mail.Read offline_access"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data) as resp:
            if resp.status == 200:
                tokens = await resp.json()
                tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
                return tokens
    return None

async def fetch_emails(access_token: str, limit: int = 5, unread_only: bool = False):
    """Fetch emails from Outlook"""
    graph_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    
    params = {
        "$top": limit,
        "$orderby": "receivedDateTime DESC",
        "$select": "subject,from,receivedDateTime,isRead"
    }
    
    if unread_only:
        params["$filter"] = "isRead eq false"
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(graph_url, headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('value', [])
    return []

def handle_auth_callback(code: str, state: str):
    """Store tokens after OAuth"""
    import asyncio
    
    try:
        user_id = int(state)
        tokens = asyncio.run(exchange_code_for_token(code))
        
        if tokens:
            config.user_tokens[user_id] = tokens
            return user_id, True
    except:
        pass
    return None, False

# ==================== APPLICATION SETUP ====================

def create_application():
    """Create Telegram bot application"""
    app = Application.builder().token(config.TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("inbox", inbox))
    app.add_handler(CommandHandler("unread", unread))
    app.add_handler(CommandHandler("disconnect", disconnect))
    app.add_handler(CommandHandler("help", help_command))
    
    return app
