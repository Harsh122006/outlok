import os
import logging
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Get from environment
TOKEN = os.getenv("TELEGRAM_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Storage for user tokens (in production use database)
user_tokens = {}

# ==================== COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Outlook Email Bot\n\n"
        "Commands:\n"
        "/connect - Link Outlook\n"
        "/inbox - Read emails\n"
        "/unread - Unread emails\n"
        "/help - Show help"
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    auth_url = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=Mail.Read%20offline_access&state={user_id}"
    
    keyboard = [[InlineKeyboardButton("🔗 Connect Outlook", url=auth_url)]]
    await update.message.reply_text(
        "Click to connect Outlook:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Read latest emails"""
    user_id = update.effective_user.id
    
    if user_id not in user_tokens:
        await update.message.reply_text("❌ Use /connect first")
        return
    
    await update.message.reply_text("📬 Fetching emails...")
    
    tokens = user_tokens[user_id]
    
    # Check if token expired
    if datetime.now() > tokens.get('expires_at', datetime.now()):
        new_tokens = refresh_access_token(tokens.get('refresh_token'))
        if new_tokens:
            user_tokens[user_id] = new_tokens
            tokens = new_tokens
        else:
            await update.message.reply_text("❌ Session expired. Use /connect again")
            return
    
    # Fetch emails
    emails = fetch_emails(tokens['access_token'])
    
    if not emails:
        await update.message.reply_text("📭 No emails found")
        return
    
    # Display emails
    response = "📧 *Latest Emails:*\n\n"
    for i, email in enumerate(emails[:5]):
        sender = email.get('from', {}).get('emailAddress', {})
        sender_name = sender.get('name', 'Unknown')
        sender_email = sender.get('address', '')
        subject = email.get('subject', 'No Subject')
        if len(subject) > 50:
            subject = subject[:47] + "..."
        received = email.get('receivedDateTime', '')[:10]
        
        response += f"*{i+1}. {subject}*\n"
        response += f"   👤 {sender_name}\n"
        if sender_email:
            response += f"   📧 {sender_email}\n"
        if received:
            response += f"   📅 {received}\n"
        response += "\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def unread(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show unread emails"""
    user_id = update.effective_user.id
    
    if user_id not in user_tokens:
        await update.message.reply_text("❌ Use /connect first")
        return
    
    await update.message.reply_text("🔵 Checking unread emails...")
    
    tokens = user_tokens[user_id]
    
    if datetime.now() > tokens.get('expires_at', datetime.now()):
        new_tokens = refresh_access_token(tokens.get('refresh_token'))
        if new_tokens:
            user_tokens[user_id] = new_tokens
            tokens = new_tokens
    
    emails = fetch_emails(tokens['access_token'], unread_only=True)
    
    if not emails:
        await update.message.reply_text("🎉 No unread emails!")
        return
    
    response = "🔵 *Unread Emails:*\n\n"
    for i, email in enumerate(emails[:5]):
        sender = email.get('from', {}).get('emailAddress', {})
        sender_name = sender.get('name', 'Unknown')
        subject = email.get('subject', 'No Subject')
        if len(subject) > 50:
            subject = subject[:47] + "..."
        
        response += f"*{i+1}. {subject}*\n"
        response += f"   👤 {sender_name}\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Help:\n"
        "/connect - Link Outlook\n"
        "/inbox - Read emails (last 5)\n"
        "/unread - Unread emails\n"
        "/help - This message"
    )

# ==================== EMAIL FUNCTIONS ====================

def fetch_emails(access_token: str, limit: int = 10, unread_only: bool = False):
    """Fetch emails from Microsoft Graph API"""
    graph_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    
    params = {
        "$top": limit,
        "$orderby": "receivedDateTime DESC",
        "$select": "subject,from,receivedDateTime,isRead,hasAttachments"
    }
    
    if unread_only:
        params["$filter"] = "isRead eq false"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(graph_url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get('value', [])
        else:
            logger.error(f"Failed to fetch emails: {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
    
    return []

def refresh_access_token(refresh_token: str):
    """Refresh expired access token"""
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "Mail.Read offline_access"
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=10)
        if response.status_code == 200:
            tokens = response.json()
            tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
            return tokens
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
    
    return None

# ==================== TOKEN STORAGE ====================

def store_user_tokens(user_id: int, code: str):
    """Store tokens after OAuth callback"""
    # Exchange code for tokens
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "scope": "Mail.Read offline_access"
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=10)
        if response.status_code == 200:
            tokens = response.json()
            tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
            user_tokens[user_id] = tokens
            return True
    except Exception as e:
        logger.error(f"Token exchange error: {e}")
    
    return False

# ==================== RUN BOT ====================

def main():
    """Start the bot"""
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN not set!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("inbox", inbox))
    app.add_handler(CommandHandler("unread", unread))
    app.add_handler(CommandHandler("help", help_command))
    
    logger.info("Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
