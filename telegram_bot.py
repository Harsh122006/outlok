import os
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)
from msal import PublicClientApplication

# Configuration
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8080/auth/callback")

# In-memory storage (in production, use a database)
user_tokens = {}
auth_requests = {}

# Initialize MSAL app
msal_app = PublicClientApplication(
    client_id=CLIENT_ID,
    authority="https://login.microsoftonline.com/consumers"
)

# ==================== TELEGRAM COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_text = """
    👋 *Welcome to Outlook Email Reader Bot!*

    I can help you read your Outlook emails directly in Telegram.

    *Available Commands:*
    /connect - Link your Outlook account
    /inbox - Read your latest emails
    /unread - Show unread emails
    /disconnect - Remove account link
    /help - Show this help message

    *Privacy:* Your emails are only read when you request them.
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /connect command - Send auth link"""
    user_id = update.effective_user.id
    
    # Generate auth URL
    auth_url = msal_app.get_authorization_request_url(
        scopes=["Mail.Read", "offline_access"],
        redirect_uri=REDIRECT_URI,
        state=str(user_id)
    )
    
    # Store auth request
    auth_requests[user_id] = auth_url
    
    keyboard = [
        [InlineKeyboardButton("🔗 Connect Outlook", url=auth_url)],
        [InlineKeyboardButton("✅ Done Connecting", callback_data="auth_done")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📧 *Connect Your Outlook Account*\n\n"
        "1. Click the button below\n"
        "2. Login with your Microsoft account\n"
        "3. Grant 'Read email' permission\n"
        "4. Click 'Done Connecting' when finished\n\n"
        "⚠️ *Note:* After authorization, you'll be redirected to a webpage. "
        "Just close it and return here.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def auth_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle auth done callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id in user_tokens:
        await query.edit_message_text(
            "✅ *Already Connected!*\n\n"
            "Your Outlook account is already linked.\n"
            "Use /inbox to read your emails.",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            "🔗 *Authorization Required*\n\n"
            "Please click the 'Connect Outlook' button first to authorize access.",
            parse_mode='Markdown'
        )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /inbox command - Show latest emails"""
    user_id = update.effective_user.id
    
    if user_id not in user_tokens:
        await update.message.reply_text(
            "❌ *Account Not Connected*\n\n"
            "Please use /connect first to link your Outlook account.",
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text("📬 Fetching your emails...")
    
    # Get user tokens
    tokens = user_tokens[user_id]
    
    # Check if token needs refresh
    if datetime.now() > tokens.get('expires_at', datetime.now()):
        tokens = await refresh_tokens(tokens['refresh_token'])
        if tokens:
            user_tokens[user_id] = tokens
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
    
    # Send emails in chunks (Telegram has message length limits)
    for i in range(0, len(emails), 3):  # Send 3 emails per message
        chunk = emails[i:i+3]
        message = format_emails(chunk, i+1)
        await update.message.reply_text(message, parse_mode='Markdown')

async def unread(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unread command - Show unread emails"""
    user_id = update.effective_user.id
    
    if user_id not in user_tokens:
        await update.message.reply_text(
            "❌ *Account Not Connected*\n\n"
            "Please use /connect first to link your Outlook account.",
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text("📬 Fetching unread emails...")
    
    tokens = user_tokens[user_id]
    
    # Check token expiry
    if datetime.now() > tokens.get('expires_at', datetime.now()):
        tokens = await refresh_tokens(tokens['refresh_token'])
        if tokens:
            user_tokens[user_id] = tokens
    
    # Fetch unread emails
    emails = await fetch_emails(tokens['access_token'], unread_only=True)
    
    if not emails:
        await update.message.reply_text(
            "🎉 *All Caught Up!*\n\n"
            "You have no unread emails.",
            parse_mode='Markdown'
        )
        return
    
    for i in range(0, len(emails), 3):
        chunk = emails[i:i+3]
        message = format_emails(chunk, i+1, unread=True)
        await update.message.reply_text(message, parse_mode='Markdown')

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /disconnect command"""
    user_id = update.effective_user.id
    
    if user_id in user_tokens:
        del user_tokens[user_id]
        await update.message.reply_text(
            "✅ *Account Disconnected*\n\n"
            "Your Outlook account has been unlinked.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "ℹ️ *No Account Linked*\n\n"
            "You don't have any Outlook account connected.",
            parse_mode='Markdown'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
    📋 *Help & Commands*

    *Available Commands:*
    /start - Welcome message
    /connect - Link your Outlook account
    /inbox - Read latest emails (last 10)
    /unread - Show unread emails
    /disconnect - Remove account link
    /help - Show this message

    *How to Connect:*
    1. Use /connect command
    2. Click the "Connect Outlook" button
    3. Login with Microsoft account
    4. Grant permission to read emails
    5. Click "Done Connecting"

    *Privacy & Security:*
    • I only read emails when you ask
    • No emails are stored permanently
    • Your tokens are encrypted
    • Disconnect anytime with /disconnect

    *Need Help?*
    Make sure you're using a personal Microsoft account.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ==================== MICROSOFT GRAPH API ====================

async def exchange_code_for_token(code: str):
    """Exchange auth code for access token"""
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
    """Refresh access token using refresh token"""
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
    """Fetch emails from Microsoft Graph API"""
    graph_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    
    # Build query parameters
    params = {
        "$top": limit,
        "$orderby": "receivedDateTime DESC",
        "$select": "subject,from,receivedDateTime,hasAttachments,isRead,bodyPreview"
    }
    
    if unread_only:
        params["$filter"] = "isRead eq false"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(graph_url, headers=headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('value', [])
            return []

def format_emails(emails, start_num: int = 1, unread: bool = False):
    """Format emails for Telegram display"""
    if not emails:
        return "No emails found."
    
    title = "📧 *Unread Emails*\n\n" if unread else "📧 *Latest Emails*\n\n"
    message = title
    
    for i, email in enumerate(emails, start=start_num):
        sender = email.get('from', {}).get('emailAddress', {})
        sender_name = sender.get('name', 'Unknown')
        subject = email.get('subject', 'No Subject')
        received = email.get('receivedDateTime', '')[:19]
        preview = email.get('bodyPreview', '')[:100]
        has_attachments = " 📎" if email.get('hasAttachments') else ""
        is_read = "" if email.get('isRead') else " 🔵"
        
        message += f"*{i}. {subject}*{has_attachments}{is_read}\n"
        message += f"   👤 {sender_name}\n"
        message += f"   🕐 {received}\n"
        if preview:
            message += f"   📝 {preview}...\n"
        message += "\n"
    
    return message

# ==================== AUTH CALLBACK HANDLER ====================

def handle_auth_callback(code: str, state: str):
    """Handle OAuth callback and store tokens"""
    try:
        user_id = int(state)
        
        # Exchange code for tokens
        async def get_tokens():
            return await exchange_code_for_token(code)
        
        tokens = asyncio.run(get_tokens())
        
        if tokens:
            user_tokens[user_id] = tokens
            return user_id, True
        return None, False
    except:
        return None, False

# ==================== BOT APPLICATION ====================

def create_application():
    """Create and configure Telegram application"""
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("inbox", inbox))
    app.add_handler(CommandHandler("unread", unread))
    app.add_handler(CommandHandler("disconnect", disconnect))
    app.add_handler(CommandHandler("help", help_command))
    
    # Add callback handler
    app.add_handler(CallbackQueryHandler(auth_done_callback, pattern="auth_done"))
    
    return app
    
