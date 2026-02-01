import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Outlook Bot")

# Try to import bot module
try:
    from telegram_bot import create_application, handle_auth_callback
    telegram_app = None
    logger.info("Successfully imported telegram_bot module")
except Exception as e:
    logger.error(f"Failed to import telegram_bot: {e}")
    telegram_app = None

@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    global telegram_app
    
    try:
        # Check required environment variables
        required_vars = ["TELEGRAM_BOT_TOKEN", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "RAILWAY_STATIC_URL"]
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            logger.error(f"Missing environment variables: {missing}")
            return
        
        # Create Telegram application
        telegram_app = create_application()
        
        # Initialize the bot
        await telegram_app.initialize()
        await telegram_app.start()
        
        # Set webhook
        WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")
        if WEBHOOK_URL:
            webhook_url = f"{WEBHOOK_URL}/webhook"
            await telegram_app.bot.set_webhook(webhook_url)
            logger.info(f"✅ Webhook set to: {webhook_url}")
        
        logger.info("✅ Bot started successfully!")
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown bot"""
    global telegram_app
    
    try:
        if telegram_app:
            await telegram_app.stop()
            await telegram_app.shutdown()
            logger.info("Bot shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# ==================== ROUTES ====================

@app.get("/")
async def root():
    """Health check endpoint"""
    try:
        return JSONResponse(
            status_code=200,
            content={
                "status": "online",
                "service": "Telegram Outlook Bot",
                "webhook_set": telegram_app is not None
            }
        )
    except Exception as e:
        logger.error(f"Root endpoint error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

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
        
        user_id, success = handle_auth_callback(code, state)
        
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
            <head><title>Connected</title></head>
            <body style="text-align: center; padding: 50px;">
                <h1>✅ Connected!</h1>
                <p>Return to Telegram</p>
                <script>setTimeout(() => window.close(), 2000)</script>
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
        reload=False,
        access_log=True
    )
