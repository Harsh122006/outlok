import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
telegram_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager (replaces on_event)"""
    global telegram_app
    
    # Startup
    logger.info("Starting Telegram Outlook Bot...")
    
    try:
        # Check required environment variables
        required_vars = ["TELEGRAM_BOT_TOKEN", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "RAILWAY_STATIC_URL"]
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            logger.error(f"Missing environment variables: {missing}")
            yield
            return
        
        # Fix URL format if needed
        railway_url = os.getenv("RAILWAY_STATIC_URL")
        if railway_url and not railway_url.startswith("http"):
            railway_url = f"https://{railway_url}"
            logger.info(f"Fixed URL to: {railway_url}")
        
        # Import and create application
        from telegram_bot import create_application
        telegram_app = create_application()
        
        # Initialize the bot
        await telegram_app.initialize()
        await telegram_app.start()
        
        # Set webhook
        if railway_url:
            webhook_endpoint = f"{railway_url}/webhook"
            await telegram_app.bot.set_webhook(webhook_endpoint)
            logger.info(f"✅ Webhook set to: {webhook_endpoint}")
        
        logger.info("✅ Bot started successfully!")
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
    
    yield  # App runs here
    
    # Shutdown
    logger.info("Shutting down bot...")
    try:
        if telegram_app:
            await telegram_app.stop()
            await telegram_app.shutdown()
            logger.info("Bot shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Create FastAPI app with lifespan
app = FastAPI(title="Telegram Outlook Bot", lifespan=lifespan)

# ==================== ROUTES ====================

@app.get("/")
async def root():
    """Health check with debug info"""
    railway_url = os.getenv("RAILWAY_STATIC_URL")
    
    # Fix URL if missing https://
    if railway_url and not railway_url.startswith("http"):
        railway_url = f"https://{railway_url}"
    
    redirect_uri = f"{railway_url}/auth/callback" if railway_url else None
    
    return {
        "status": "online",
        "service": "Telegram Outlook Bot",
        "railway_url": railway_url,
        "redirect_uri": redirect_uri,
        "bot_running": telegram_app is not None
    }

@app.get("/health")
async def health():
    """Simple health check"""
    return {"status": "ok"}

@app.get("/auth/callback")
async def auth_callback(code: str = None, state: str = None):
    """Handle Microsoft OAuth callback"""
    try:
        if not code or not state:
            raise HTTPException(status_code=400, detail="Missing parameters")
        
        from telegram_bot import handle_auth_callback as handle_callback
        user_id, success = handle_callback(code, state)
        
        if success and user_id and telegram_app:
            try:
                await telegram_app.bot.send_message(
                    chat_id=user_id,
                    text="✅ Outlook Connected! Use /inbox to read emails."
                )
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")
        
        # Simple success page
        html = """
        <html>
            <head>
                <title>Connected</title>
                <style>
                    body { text-align: center; padding: 50px; font-family: Arial; }
                    .success { color: green; font-size: 4em; }
                </style>
            </head>
            <body>
                <div class="success">✅</div>
                <h1>Outlook Connected!</h1>
                <p>You can close this window and return to Telegram.</p>
                <script>setTimeout(() => window.close(), 3000)</script>
            </body>
        </html>
        """
        return HTMLResponse(content=html)
        
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle Telegram webhook updates"""
    try:
        if not telegram_app:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Bot not initialized"}
            )
        
        data = await request.json()
        
        from telegram import Update
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)}
        )

# ==================== MAIN ====================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )
    
