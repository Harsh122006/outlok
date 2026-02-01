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
        
        # Validate RAILWAY_STATIC_URL
        webhook_url = os.getenv("RAILWAY_STATIC_URL", "")
        if not webhook_url.startswith("http"):
            logger.error(f"Invalid RAILWAY_STATIC_URL: {webhook_url}")
            return
        
        logger.info(f"Using webhook URL: {webhook_url}")
        
        # Create Telegram application
        telegram_app = create_application()
        
        # Initialize the bot
        await telegram_app.initialize()
        await telegram_app.start()
        
        # Set webhook
        webhook_url = os.getenv("RAILWAY_STATIC_URL")
        if webhook_url:
            # Ensure proper webhook URL
            if not webhook_url.startswith("http"):
                webhook_url = f"https://{webhook_url}"
            
            webhook_endpoint = f"{webhook_url}/webhook"
            await telegram_app.bot.set_webhook(webhook_endpoint)
            logger.info(f"✅ Webhook set to: {webhook_endpoint}")
        
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
        webhook_url = os.getenv("RAILWAY_STATIC_URL", "")
        redirect_uri = f"https://{webhook_url.split('//')[-1]}/auth/callback" if webhook_url else "Not set"
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "online",
                "service": "Telegram Outlook Bot",
                "webhook_url": webhook_url,
                "redirect_uri": redirect_uri,
                "bot_running": telegram_app is not None
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
            <head>
                <title>Connected</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        text-align: center;
                        padding: 50px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        min-height: 100vh;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        margin: 0;
                    }
                    .container {
                        background: rgba(255, 255, 255, 0.1);
                        padding: 40px;
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 style="font-size: 3em;">✅</h1>
                    <h1>Outlook Connected!</h1>
                    <p>You can close this window and return to Telegram.</p>
                </div>
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

@app.get("/debug")
async def debug():
    """Debug info"""
    webhook_url = os.getenv("RAILWAY_STATIC_URL", "")
    redirect_uri = f"https://{webhook_url.split('//')[-1]}/auth/callback" if webhook_url else "Not set"
    
    return {
        "webhook_url": webhook_url,
        "redirect_uri": redirect_uri,
        "bot_running": telegram_app is not None
    }

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
