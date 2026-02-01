import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Try to import bot
try:
    from telegram_bot import create_application
    telegram_app = None
except ImportError as e:
    logger.error(f"Import error: {e}")
    telegram_app = None

@app.get("/")
async def root():
    return JSONResponse(
        content={
            "status": "online",
            "service": "Telegram Bot",
            "port": os.getenv("PORT", 8000)
        }
    )

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/webhook")
async def webhook(request: Request):
    if telegram_app:
        try:
            data = await request.json()
            from telegram import Update
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.process_update(update)
            return {"ok": True}
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "Bot not initialized"}

@app.on_event("startup")
async def startup():
    global telegram_app
    try:
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return
            
        telegram_app = create_application()
        await telegram_app.initialize()
        await telegram_app.start()
        
        # Set webhook
        railway_url = os.getenv("RAILWAY_STATIC_URL")
        if railway_url:
            if not railway_url.startswith("http"):
                railway_url = f"https://{railway_url}"
            webhook_url = f"{railway_url}/webhook"
            await telegram_app.bot.set_webhook(webhook_url)
            logger.info(f"Webhook set: {webhook_url}")
        
        logger.info("✅ Bot started")
    except Exception as e:
        logger.error(f"Startup error: {e}")

@app.on_event("shutdown")
async def shutdown():
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
