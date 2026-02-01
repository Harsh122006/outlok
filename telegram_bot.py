import os
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from msal import PublicClientApplication

# Configuration
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")
REDIRECT_URI = f"{WEBHOOK_URL}/auth/callback" if WEBHOOK_URL else None

# In-memory storage (for demo)
user_tokens = {}

# MSAL app for auth URLs
msal_app = PublicClientApplication(
    client_id=CLIENT_ID,
    authority="https://login.microsoftonline.com/consumers"
)

# ==================== TELEGRAM COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "👋 *Outlook Email Reader Bot*\n\n"
        "I can read your Outlook emails!\n\n"
        "*Commands:*\n"
        "/connect - Link Outlook account\n"
        "/inbox - Read latest emails\n"
        "/unread - Show unread emails\n"
        "/disconnect - Remove account\n"
        "/help - Show help\n\n"
        "Start with /connect to authorize.",
        parse_mode='Markdown'
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate Outlook auth link"""
    user_id = update.effective_user.id
    
    # Generate auth URL
    auth_url = msal_app.get_authorization_request_url(
        scopes=["Mail.Read", "offline_access"],
        redirect_uri=REDIRECT_URI,
        state=str(user_id)
    )
    
    # Create inline keyboard with auth link
    keyboard = [[InlineKeyboardButton("🔗 Connect Outlook", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📧 *Connect Your Outlook Account*\n\n"
        "1. Click the button below\n"
        "2. Login with your Microsoft account\n"
        "3. Grant 'Read email' permission\n"
        "4. Return to Telegram after authorization\n\n"
        "⚠️ *Note:* You'll be redirected to a webpage. Just close it after authorization.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Read latest emails"""
    user_id = update.effective_user.id
    
    if user_id not in user_tokens:
        await update.message.reply_text(
            "❌ *Account Not Connected*\n\n"
            "Please use /connect first to link your Outlook account.",
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text("📬 Fetching your emails...")
    
    tokens = user_tokens[user_id]
    
    # Check token expiry
    if datetime.now() > tokens.get('expires_at', datetime.now()):
        new_tokens = await refresh_tokens(tokens['refresh_token'])
        if new_tokens:
            user_tokens[user_id] = new_tokens
            tokens = new_tokens
        else:
            await update.message.reply_text(
                "❌ *Session Expired*\n\n"
                "Please reconnect with /connect",
                parse_mode='Markdown'
            )
            return
    
    # Fetch emails
    emails = await fetch_emails(tokens['access_token'])
    
    if not emails:
        await update.message.reply_text(
            "📭 *No Emails Found*\n\n"
            "Your inbox is empty or I couldn't fetch emails.",
            parse_mode='Markdown'
        )
        return
    
    # Format and send emails
    response = "📧 *Latest Emails:*\n\n"
    
    for i, email in enumerate(emails[:5]):  # Show first 5 emails
        sender = email.get('from', {}).get('emailAddress', {})
        sender_name = sender.get('name', 'Unknown')
        subject = email.get('subject', 'No Subject')
        if len(subject) > 50:
            subject = subject[:47] + "..."
        
        received = email.get('receivedDateTime', '')
        if received:
            received = received[:10]  # Just the date
        
        has_attachments = "📎" if email.get('hasAttachments') else ""
        is_read = "" if email.get('isRead') else "🔵 "
        
        response += f"{is_read}**{i+1}. {subject}** {has_attachments}\n"
        response += f"   👤 {sender_name}\n"
        if received:
            response += f"   📅 {received}\n"
        response += "\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def unread(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show unread emails"""
    user_id = update.effective_user.id
    
    if user_id not in user_tokens:
        await update.message.reply_text("❌ Use /connect first", parse_mode='Markdown')
        return
    
    await update.message.reply_text("🔵 Checking unread emails...")
    
    tokens = user_tokens[user_id]
    
    if datetime.now() > tokens.get('expires_at', datetime.now()):
        new_tokens = await refresh_tokens(tokens['refresh_token'])
        if new_tokens:
            user_tokens[user_id] = new_tokens
            tokens = new_tokens
    
    emails = await fetch_emails(tokens['access_token'], unread_only=True)
    
    if not emails:
        await update.message.reply_text("🎉 *All Caught Up!*\nNo unread emails.", parse_mode='Markdown')
        return
    
    response = "🔵 *Unread Emails:*\n\n"
    for i, email in enumerate(emails[:5]):
        sender = email.get('from', {}).get('emailAddress', {})
        sender_name = sender.get('name', 'Unknown')
        subject = email.get('subject', 'No Subject')
        if len(subject) > 50:
            subject = subject[:47] + "..."
        
        response += f"**{i+1}. {subject}**\n"
        response += f"   👤 {sender_name}\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove account"""
    user_id = update.effective_user.id
    
    if user_id in user_tokens:
        del user_tokens[user_id]
        await update.message.reply_text("✅ *Account Disconnected*\nYour Outlook account has been unlinked.", parse_mode='Markdown')
    else:
        await update.message.reply_text("ℹ️ *No Account Linked*", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    await update.message.reply_text(
        "📋 *Help & Commands*\n\n"
        "/start - Welcome message\n"
        "/connect - Link Outlook account\n"
        "/inbox - Read latest emails\n"
        "/unread - Show unread emails\n"
        "/disconnect - Remove account\n"
        "/help - Show this message\n\n"
        "*Privacy:*\n"
        "• I only read emails when you ask\n"
        "• No emails are stored permanently\n"
        "• Disconnect anytime with /disconnect",
        parse_mode='Markdown'
    )

# ==================== MICROSOFT GRAPH API ====================

async def exchange_code_for_token(code: str):
    """Exchange auth code for tokens"""
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "scope": "Mail.Read offline_access"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data) as response:
            if response.status == 200:
                tokens = await response.json()
                # Add expiry time
                tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
                return tokens
    return None

async def refresh_tokens(refresh_token: str):
    """Refresh access token"""
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "Mail.Read offline_access"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data) as response:
            if response.status == 200:
                tokens = await response.json()
                tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
                return tokens
    return None

async def fetch_emails(access_token: str, limit: int = 10, unread_only: bool = False):
    """Fetch emails from Outlook"""
    graph_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    
    params = {
        "$top": limit,
        "$orderby": "receivedDateTime DESC",
        "$select": "subject,from,receivedDateTime,hasAttachments,isRead"
    }
    
    if unread_only:
        params["$filter"] = "isRead eq false"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(graph_url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('value', [])
                return []
    except:
        return []

# ==================== AUTH HANDLER ====================

def handle_auth_callback(code: str, state: str):
    """Process OAuth callback and store tokens"""
    try:
        user_id = int(state)
        
        # Exchange code for tokens (run async in sync context)
        async def get_tokens():
            return await exchange_code_for_token(code)
        
        tokens = asyncio.run(get_tokens())
        
        if tokens:
            user_tokens[user_id] = tokens
            return user_id, True
    except:
        pass
    return None, False

# ==================== CREATE APPLICATION ====================

def create_application():
    """Create Telegram bot application"""
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("connect", connect))
    application.add_handler(CommandHandler("inbox", inbox))
    application.add_handler(CommandHandler("unread", unread))
    application.add_handler(CommandHandler("disconnect", disconnect))
    application.add_handler(CommandHandler("help", help_command))
    
    return application
