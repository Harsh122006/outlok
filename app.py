import os
import asyncio
import urllib.parse
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== ENV ==================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
TENANT = os.getenv("MS_TENANT_ID", "common")
REDIRECT_URI = os.getenv("REDIRECT_URI")

AUTH_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"

SCOPES = "Mail.Read offline_access User.Read"

# ================== MEMORY STORE (TEMP) ==================
# telegram_id -> token dict
TOKENS = {}

# ================== FASTAPI ==================
api = FastAPI()

@api.get("/auth/callback")
async def auth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")  # telegram user id

    if not code or not state:
        return HTMLResponse("Missing code or state", status_code=400)

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    }

    res = requests.post(TOKEN_URL, data=data).json()

    if "access_token" not in res:
        return HTMLResponse(f"OAuth failed: {res}", status_code=400)

    TOKENS[state] = res

    return HTMLResponse(
        "<h2>✅ Outlook connected successfully</h2>You can return to Telegram."
    )

# ================== TELEGRAM ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Use /connect to link your Outlook account."
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": SCOPES,
        "state": telegram_id,  # link OAuth → Telegram user
    }

    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    await update.message.reply_text(
        "🔐 Click to connect your Outlook account:\n\n" + url
    )

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)

    if telegram_id not in TOKENS:
        await update.message.reply_text("❌ Not connected. Use /connect first.")
        return

    token = TOKENS[telegram_id]["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$top=5",
        headers=headers,
    )

    data = r.json()

    if "value" not in data:
        await update.message.reply_text("Failed to fetch emails.")
        return

    msg = "📬 Latest emails:\n\n"
    for mail in data["value"]:
        msg += f"• {mail['subject']}\n"

    await update.message.reply_text(msg)

# ================== RUN BOTH ==================
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("inbox", inbox))

    await app.initialize()
    await app.start()

    import uvicorn
    config = uvicorn.Config(api, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    await asyncio.gather(server.serve())

if __name__ == "__main__":
    asyncio.run(main())
