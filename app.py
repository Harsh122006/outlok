import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# Import from telegram_bot
from telegram_bot import create_application, handle_auth_callback, user_tokens

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable for Telegram app
telegram_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for startup/shutdown events"""
    global telegram_app
    
    # Startup
    logger.info("Starting Telegram Outlook Bot...")
    
    # Create Telegram application
    telegram_app = create_application()
    
    # Initialize the bot
    await telegram_app.initialize()
    await telegram_app.start()
    
    # Set webhook for production
    WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await telegram_app.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook set to: {webhook_url}")
    else:
        logger.warning("WEBHOOK_URL not set, webhook not configured")
    
    logger.info("✅ Bot started successfully!")
    
    yield  # App runs here
    
    # Shutdown
    logger.info("Shutting down Telegram Outlook Bot...")
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()
    logger.info("Bot shutdown complete")

# Initialize FastAPI app with lifespan
app = FastAPI(title="Telegram Outlook Bot", lifespan=lifespan)

# ==================== ROUTES ====================

@app.get("/")
async def root():
    """Health check endpoint"""
    WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")
    return {
        "status": "online",
        "service": "Telegram Outlook Bot",
        "webhook": f"{WEBHOOK_URL}/webhook" if WEBHOOK_URL else "Not set",
        "connected_users": len(user_tokens)
    }

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}

@app.get("/auth/callback")
async def auth_callback(code: str = None, state: str = None):
    """Handle Microsoft OAuth callback"""
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")
    
    # Process the auth callback
    user_id, success = handle_auth_callback(code, state)
    
    if success and user_id and telegram_app:
        # Send confirmation message to user
        try:
            await telegram_app.bot.send_message(
                chat_id=user_id,
                text="✅ *Outlook Connected Successfully!*\n\n"
                     "You can now use:\n"
                     "• /inbox - Read your latest emails\n"
                     "• /unread - Show unread emails\n\n"
                     "Happy email reading! 📧",
                parse_mode='Markdown'
            )
            logger.info(f"Sent confirmation to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
    
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
                margin-bottom: 2rem;
            }
            .button {
                display: inline-block;
                padding: 0.8rem 2rem;
                background: white;
                color: #667eea;
                border: none;
                border-radius: 50px;
                font-size: 1rem;
                font-weight: bold;
                cursor: pointer;
                text-decoration: none;
                transition: transform 0.2s;
            }
            .button:hover {
                transform: scale(1.05);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <h1>Successfully Connected!</h1>
            <p>Your Outlook account is now linked with the Telegram bot.</p>
            <p>You can close this window and return to Telegram.</p>
            <button class="button" onclick="window.close()">Close Window</button>
        </div>
        <script>
            // Auto-close after 3 seconds
            setTimeout(() => {
                window.close();
            }, 3000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle Telegram webhook updates"""
    try:
        # Parse incoming update
        data = await request.json()
        
        # Process the update using the bot's update processor
        from telegram import Update
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )

@app.get("/debug")
async def debug():
    """Debug endpoint"""
    WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")
    return {
        "connected_users": len(user_tokens),
        "user_ids": list(user_tokens.keys()),
        "webhook_url": f"{WEBHOOK_URL}/webhook" if WEBHOOK_URL else None,
        "bot_running": telegram_app is not None
    }

@app.get("/set-webhook")
async def set_webhook():
    """Manually set webhook"""
    WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")
    if not WEBHOOK_URL or not telegram_app:
        return {"error": "WEBHOOK_URL not set or bot not initialized"}
    
    webhook_url = f"{WEBHOOK_URL}/webhook"
    result = await telegram_app.bot.set_webhook(webhook_url)
    
    return {
        "success": result,
        "webhook_url": webhook_url,
        "bot_username": (await telegram_app.bot.get_me()).username
    }

# ==================== MAIN ENTRY POINT ====================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
