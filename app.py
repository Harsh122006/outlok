import os
import threading
import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import telegram_bot

app = FastAPI()

CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
TENANT = os.getenv("MS_TENANT_ID", "common")

TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"


@app.get("/")
def home():
    return {"status": "running"}


@app.get("/auth/callback")
async def auth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return PlainTextResponse("Missing code or state")

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "scope": "offline_access Mail.Read",
    }

    token = requests.post(TOKEN_URL, data=data).json()

    if "access_token" not in token:
        return PlainTextResponse(f"Token error: {token}")

    return PlainTextResponse(
        "✅ Outlook connected successfully! You can return to Telegram."
    )


def start_telegram_bot():
    print("🤖 Starting Telegram bot...")
    telegram_bot.run_bot()


if __name__ == "__main__":
    # 🔥 Start Telegram bot in background
    threading.Thread(target=start_telegram_bot, daemon=True).start()

    # 🚀 Start FastAPI server (THIS KEEPS CONTAINER ALIVE)
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
