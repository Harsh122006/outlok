import os
import logging
import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from sqlalchemy.orm import Session

from database import get_db, UserToken, init_db
from auth import generate_auth_url, exchange_code_for_token, refresh_access_token
from email_service import fetch_user_emails

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL", os.getenv("WEBHOOK_URL"))
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
REDIRECT_URI = f"{WEBHOOK_URL}/auth/callback" if WEBHOOK_URL else None
PORT = int(os.getenv("PORT", 8000))

# Validate required environment variables
if not all([TOKEN, CLIENT_ID, CLIENT_SECRET, WEBHOOK_URL]):
    missing = []
    if not TOKEN: missing.append("TELEGRAM_BOT_TOKEN")
    if not CLIENT_ID: missing.append("MS_CLIENT_ID")
    if not CLIENT_SECRET: missing.append("MS_CLIENT_SECRET")
    if not WEBHOOK_URL: missing.append("RAILWAY_STATIC_URL/WEBHOOK_URL")
    logger.warning(f"Missing environment variables: {', '.join(missing)}")

# Global bot instance
bot = None
telegram_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for startup/shutdown events"""
    # Startup
    global bot, telegram_app
    
    logger.info("Starting Telegram Outlook Bot...")
    
    # Initialize database
    init_db()
    
    # Initialize Telegram bot
    bot = Bot(token=TOKEN)
    telegram_app = Application.builder().token(TOKEN).build()
    
    # Register command handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("connect", connect))
    telegram_app.add_handler(CommandHandler("inbox", inbox))
    telegram_app.add_handler(CommandHandler("disconnect", disconnect))
    telegram_app.add_handler(CommandHandler("help", help_command))
    
    await telegram_app.initialize()
    
    # Set webhook
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await telegram_app.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Telegram Outlook Bot...")
    await telegram_app.shutdown()

# Create FastAPI app with lifespan
app = FastAPI(title="Telegram Outlook Bot", lifespan=lifespan)

# ==================== TELEGRAM COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "I'm your Outlook Email Assistant! 📧\n\n"
        "**Available Commands:**\n"
        "/connect - Link your Outlook account\n"
        "/inbox - View your latest emails\n"
        "/disconnect - Remove account link\n"
        "/help - Show help information\n\n"
        "First, use /connect to authorize access to your Outlook emails."
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /connect command"""
    user_id = update.effective_user.id
    
    # Generate auth URL
    auth_url = generate_auth_url(user_id, CLIENT_ID, REDIRECT_URI)
    
    if not auth_url:
        await update.message.reply_text(
            "❌ Sorry, I couldn't generate the authentication link. "
            "Please try again later or contact support."
        )
        return
    
    await update.message.reply_text(
        "🔗 **Connect Your Outlook Account**\n\n"
        "1. Click this link to authorize:\n"
        f"{auth_url}\n\n"
        "2. Login with your Microsoft account\n"
        "3. Grant permission to read your emails\n\n"
        "⚠️ *After authorization, close the browser tab and return here.*\n"
        "You'll receive a confirmation message when connected."
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /inbox command"""
    user_id = update.effective_user.id
    db = next(get_db())
    
    try:
        # Get user tokens from database
        user_token = db.query(UserToken).filter(
            UserToken.telegram_user_id == str(user_id)
        ).first()
        
        if not user_token:
            await update.message.reply_text(
                "❌ No Outlook account connected.\n"
                "Use /connect to link your account first."
            )
            return
        
        # Check if token needs refresh
        tokens = {
            'access_token': user_token.access_token,
            'refresh_token': user_token.refresh_token,
            'expires_at': user_token.expires_at.isoformat() if user_token.expires_at else None
        }
        
        if datetime.now() > user_token.expires_at:
            logger.info(f"Refreshing token for user {user_id}")
            new_tokens = await refresh_access_token(
                tokens['refresh_token'], 
                CLIENT_ID, 
                CLIENT_SECRET
            )
            
            if new_tokens:
                # Update tokens in database
                user_token.access_token = new_tokens['access_token']
                user_token.refresh_token = new_tokens['refresh_token']
                user_token.expires_at = datetime.fromisoformat(new_tokens['expires_at'])
                db.commit()
                tokens = new_tokens
            else:
                await update.message.reply_text(
                    "❌ Session expired. Please reconnect with /connect"
                )
                return
        
        # Fetch emails
        await update.message.reply_text("📬 Fetching your emails...")
        
        emails = await fetch_user_emails(tokens['access_token'])
        
        if not emails:
            await update.message.reply_text(
                "📭 Your inbox is empty or I couldn't fetch emails.\n"
                "Make sure you have emails in your Outlook inbox."
            )
            return
        
        # Format and send emails
        response = "📧 **Latest Emails:**\n\n"
        
        for i, email in enumerate(emails[:5]):  # Limit to 5 emails
            sender_name = email.get('from', {}).get('emailAddress', {}).get('name', 'Unknown')
            sender_email = email.get('from', {}).get('emailAddress', {}).get('address', '')
            subject = email.get('subject', 'No Subject')
            received = email.get('receivedDateTime', '')[:16]
            has_attachments = "📎" if email.get('hasAttachments', False) else ""
            is_read = "" if email.get('isRead', False) else "🔵 "
            
            response += f"{is_read}**{i+1}. {subject}** {has_attachments}\n"
            response += f"   👤 {sender_name}\n"
            response += f"   📧 {sender_email}\n"
            response += f"   🕐 {received}\n"
            response += "   " + "─" * 30 + "\n\n"
        
        response += f"\n📊 *Showing {min(len(emails), 5)} of {len(emails)} emails*"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error fetching emails for user {user_id}: {e}")
        await update.message.reply_text(
            "❌ Failed to fetch emails. Please try again later.\n"
            f"Error: {str(e)[:100]}"
        )
    finally:
        db.close()

async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /disconnect command"""
    user_id = update.effective_user.id
    db = next(get_db())
    
    try:
        user_token = db.query(UserToken).filter(
            UserToken.telegram_user_id == str(user_id)
        ).first()
        
        if user_token:
            db.delete(user_token)
            db.commit()
            await update.message.reply_text(
                "✅ Outlook account disconnected successfully!\n"
                "Your access tokens have been removed."
            )
        else:
            await update.message.reply_text(
                "ℹ️ No Outlook account is currently connected."
            )
    except Exception as e:
        logger.error(f"Error disconnecting user {user_id}: {e}")
        await update.message.reply_text("❌ Failed to disconnect account.")
    finally:
        db.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "📋 **Help & Support**\n\n"
        "**Commands:**\n"
        "/start - Welcome message\n"
        "/connect - Link Outlook account\n"
        "/inbox - View latest emails\n"
        "/disconnect - Remove account\n"
        "/help - This message\n\n"
        "**How it works:**\n"
        "1. Use /connect to authorize\n"
        "2. Login with Microsoft\n"
        "3. Use /inbox to read emails\n\n"
        "**Privacy:**\n"
        "• I only read your emails (Mail.Read permission)\n"
        "• No emails are stored permanently\n"
        "• You can disconnect anytime with /disconnect\n\n"
        "**Need help?**\n"
        "Contact support if you encounter issues."
    )

# ==================== FASTAPI ROUTES ====================

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
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )

@app.get("/auth/callback")
async def auth_callback(code: str, state: str = None):
    """Handle OAuth callback from Microsoft"""
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")
    
    try:
        # Extract user_id from state
        user_id = int(state)
        
        # Exchange code for tokens
        tokens = await exchange_code_for_token(
            code, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI
        )
        
        if not tokens:
            raise HTTPException(status_code=400, detail="Failed to obtain access tokens")
        
        # Save tokens to database
        db = next(get_db())
        try:
            user_token = db.query(UserToken).filter(
                UserToken.telegram_user_id == str(user_id)
            ).first()
            
            expires_at = datetime.fromisoformat(tokens['expires_at'])
            
            if user_token:
                user_token.access_token = tokens['access_token']
                user_token.refresh_token = tokens['refresh_token']
                user_token.expires_at = expires_at
            else:
                user_token = UserToken(
                    telegram_user_id=str(user_id),
                    access_token=tokens['access_token'],
                    refresh_token=tokens['refresh_token'],
                    expires_at=expires_at
                )
                db.add(user_token)
            
            db.commit()
            
            # Notify user in Telegram
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="✅ **Successfully Connected!**\n\n"
                         "Your Outlook account is now linked.\n"
                         "Use /inbox to view your latest emails."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
        finally:
            db.close()
        
        # Return success HTML page
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Outlook Connected</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-align: center;
                }
                .container {
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    padding: 3rem;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    max-width: 500px;
                    width: 90%;
                }
                .success-icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                h1 {
                    font-size: 2.5rem;
                    margin-bottom: 1rem;
                }
                p {
                    font-size: 1.2rem;
                    opacity: 0.9;
                    line-height: 1.6;
                }
                .close-btn {
                    display: inline-block;
                    margin-top: 2rem;
                    padding: 0.8rem 2rem;
                    background: white;
                    color: #667eea;
                    border: none;
                    border-radius: 50px;
                    font-size: 1rem;
                    font-weight: bold;
                    cursor: pointer;
                    transition: transform 0.2s;
                }
                .close-btn:hover {
                    transform: scale(1.05);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h1>Connected Successfully!</h1>
                <p>Your Outlook account is now linked with the Telegram bot.</p>
                <p>You can close this window and return to Telegram to start using the bot.</p>
                <button class="close-btn" onclick="window.close()">Close Window</button>
            </div>
            <script>
                // Auto-close after 5 seconds
                setTimeout(() => {
                    window.close();
                }, 5000);
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content, status_code=200)
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Telegram Outlook Bot",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "health": "/health",
            "webhook_info": "/webhook-info",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    db_healthy = False
    bot_healthy = False
    
    # Check database
    try:
        db = next(get_db())
        db.execute("SELECT 1")
        db_healthy = True
        db.close()
    except:
        pass
    
    # Check bot
    try:
        bot_info = await bot.get_me()
        bot_healthy = bool(bot_info)
    except:
        pass
    
    return {
        "status": "healthy" if all([db_healthy, bot_healthy]) else "degraded",
        "components": {
            "database": "healthy" if db_healthy else "unhealthy",
            "telegram_bot": "healthy" if bot_healthy else "unhealthy",
            "microsoft_auth": "ready" if all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI]) else "not_configured"
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/webhook-info")
async def get_webhook_info():
    """Check webhook status"""
    try:
        info = await telegram_app.bot.get_webhook_info()
        return {
            "url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date,
            "last_error_message": info.last_error_message,
            "max_connections": info.max_connections,
            "allowed_updates": info.allowed_updates
        }
    except Exception as e:
        return {"error": str(e)}

# ==================== MAIN ENTRY POINT ====================

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on port {PORT}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,  # Disable auto-reload in production
        log_level="info"
    )
