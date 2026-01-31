import os
import json
import asyncio
from datetime import datetime, timedelta
from fastapi.responses import HTMLResponse  # Add this import
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import aiohttp
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL", os.getenv("WEBHOOK_URL"))
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
PORT = int(os.getenv("PORT", 8000))

# Construct redirect URI for Railway
REDIRECT_URI = f"{WEBHOOK_URL}/auth/callback"

# In-memory storage (use Railway PostgreSQL in production)
user_tokens = {}
user_states = {}

app = FastAPI(title="Telegram Outlook Bot")

# Initialize Telegram bot
telegram_app = Application.builder().token(TOKEN).build()
bot = Bot(token=TOKEN)

# ---------------- TELEGRAM COMMANDS ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"👋 Hello {update.effective_user.first_name}!\n\n"
        "I can help you read your Outlook emails.\n\n"
        "Use /connect to link your Outlook account\n"
        "Use /inbox to see your latest emails\n"
        "Use /disconnect to remove your account"
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /connect command - Send OAuth link"""
    user_id = update.effective_user.id
    
    # Generate state parameter for security
    import secrets
    state = secrets.token_urlsafe(16)
    user_states[user_id] = state
    
    # Microsoft OAuth URL
    auth_url = (
        f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=offline_access%20Mail.Read"
        f"&state={user_id}:{state}"  # Embed user_id and state
        f"&response_mode=query"
    )
    
    await update.message.reply_text(
        "🔗 **Connect Your Outlook Account**\n\n"
        "Click the link below to authorize access to your emails:\n\n"
        f"{auth_url}\n\n"
        "⚠️ *Important:* After authorization, you'll be redirected to a webpage. "
        "Just close it and return to Telegram. Your account will be linked automatically!"
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /inbox command - Show latest emails"""
    user_id = update.effective_user.id
    
    if user_id not in user_tokens:
        await update.message.reply_text(
            "❌ Please connect your Outlook account first using /connect"
        )
        return
    
    tokens = user_tokens[user_id]
    
    if datetime.now() > datetime.fromisoformat(tokens.get('expires_at')):
        # Refresh token if expired
        tokens = await refresh_access_token(tokens['refresh_token'])
        if tokens:
            user_tokens[user_id] = tokens
        else:
            await update.message.reply_text(
                "❌ Session expired. Please reconnect with /connect"
            )
            return
    
    # Fetch emails from Microsoft Graph
    emails = await fetch_emails(tokens['access_token'])
    
    if not emails:
        await update.message.reply_text("📭 No emails found in your inbox.")
        return
    
    response = "📧 **Your Latest Emails:**\n\n"
    for i, email in enumerate(emails[:5]):  # Show first 5 emails
        sender = email.get('from', {}).get('emailAddress', {}).get('name', 'Unknown')
        subject = email.get('subject', 'No Subject')
        received = email.get('receivedDateTime', '')[:10]
        
        response += f"**{i+1}. {subject}**\n"
        response += f"   👤 From: {sender}\n"
        response += f"   📅 Date: {received}\n\n"
    
    await update.message.reply_text(response)

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /disconnect command"""
    user_id = update.effective_user.id
    
    if user_id in user_tokens:
        del user_tokens[user_id]
        await update.message.reply_text("✅ Outlook account disconnected successfully!")
    else:
        await update.message.reply_text("ℹ️ No Outlook account is currently connected.")

# Register command handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("connect", connect))
telegram_app.add_handler(CommandHandler("inbox", inbox))
telegram_app.add_handler(CommandHandler("disconnect", disconnect))

# ---------------- MICROSOFT GRAPH FUNCTIONS ---------------- #

async def exchange_code_for_token(code: str):
    """Exchange authorization code for access token"""
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
                # Add expiration time
                tokens['expires_at'] = (
                    datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
                ).isoformat()
                return tokens
            else:
                logger.error(f"Token exchange failed: {await response.text()}")
                return None

async def refresh_access_token(refresh_token: str):
    """Refresh expired access token"""
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
                tokens['expires_at'] = (
                    datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
                ).isoformat()
                return tokens
            else:
                logger.error(f"Token refresh failed: {await response.text()}")
                return None

async def fetch_emails(access_token: str, limit: int = 10):
    """Fetch emails from Microsoft Graph API"""
    graph_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    params = {
        "$top": limit,
        "$orderby": "receivedDateTime DESC",
        "$select": "subject,from,receivedDateTime,hasAttachments,isRead"
    }
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(graph_url, headers=headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('value', [])
            else:
                logger.error(f"Failed to fetch emails: {await response.text()}")
                return []

# ---------------- FASTAPI ROUTES ---------------- #

@app.get("/auth/callback")
async def auth_callback(code: str, state: str):
    """Handle OAuth callback from Microsoft"""
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
    
    try:
        # state format: "user_id:random_token"
        user_id_str, state_token = state.split(":")
        user_id = int(user_id_str)
        
        # Verify state token
        if user_id not in user_states or user_states[user_id] != state_token:
            raise HTTPException(status_code=400, detail="Invalid state token")
        
        # Exchange code for tokens
        tokens = await exchange_code_for_token(code)
        
        if not tokens:
            raise HTTPException(status_code=400, detail="Failed to get tokens")
        
        # Store tokens for the user
        user_tokens[user_id] = tokens
        
        # Clean up state
        del user_states[user_id]
        
        # Notify user in Telegram
        try:
            await bot.send_message(
                chat_id=user_id,
                text="✅ **Outlook account connected successfully!**\n\n"
                     "You can now use /inbox to view your latest emails."
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")
        
        # Return success page
        html_content = """
        <html>
            <head>
                <title>Outlook Connected</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .success { color: green; font-size: 24px; }
                    .info { color: #666; margin-top: 20px; }
                </style>
            </head>
            <body>
                <div class="success">✅ Outlook Connected Successfully!</div>
                <div class="info">You can close this window and return to Telegram.</div>
                <script>
                    setTimeout(function() { window.close(); }, 3000);
                </script>
            </body>
        </html>
        """
        
        return HTMLResponse(content=html_content, status_code=200)
        
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle Telegram webhook updates"""
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Telegram Outlook Bot",
        "webhook_set": telegram_app.bot._webhook_url is not None
    }

@app.get("/users")
async def list_users():
    """Debug endpoint to see connected users (remove in production)"""
    return {
        "user_count": len(user_tokens),
        "users": list(user_tokens.keys())
    }

# ---------------- STARTUP/SHUTDOWN ---------------- #

@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    logger.info("Starting up Telegram Outlook Bot...")
    
    # Initialize bot
    await telegram_app.initialize()
    
    # Set webhook for Railway
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await telegram_app.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
    else:
        logger.warning("WEBHOOK_URL not set, using polling instead")
        # Start polling in background
        await telegram_app.start()
    
    logger.info("Bot started successfully!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown"""
    logger.info("Shutting down...")
    await telegram_app.shutdown()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
