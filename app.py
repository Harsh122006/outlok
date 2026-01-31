import os
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ================== ENV ==================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://xxxx.up.railway.app

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or WEBHOOK_URL")

# ================== APP ==================
app = FastAPI()

telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# ================== BOT COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Outlook Mail Bot!\n\n"
        "Use /connect to link your Outlook account."
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth_url = (
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        "?client_id=YOUR_CLIENT_ID"
        "&response_type=code"
        f"&redirect_uri={WEBHOOK_URL}/auth/callback"
        "&response_mode=query"
        "&scope=offline_access Mail.Read"
    )
    await update.message.reply_text(
        "🔐 Click below to connect Outlook:\n\n" + auth_url
    )

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("connect", connect))

# ================== STARTUP ==================
@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    print("✅ Telegram webhook registered")

# ================== TELEGRAM WEBHOOK ==================
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

# ================== OAUTH CALLBACK ==================
@app.get("/auth/callback")
async def auth_callback(code: str | None = None, error: str | None = None):
    if error:
        return PlainTextResponse(f"OAuth error: {error}", status_code=400)

    if not code:
        return PlainTextResponse("Missing code", status_code=400)

    # 🔜 NEXT STEP: exchange code for access token
    print("✅ OAuth code received:", code)

    return PlainTextResponse(
        "✅ Outlook connected successfully.\n"
        "You can return to Telegram."
    )

# ================== HEALTH ==================
@app.get("/")
async def health():
    return {"status": "ok"}
