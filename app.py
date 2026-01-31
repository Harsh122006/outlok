import os
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from telegram_bot import start_bot
import httpx

app = FastAPI()

CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

@app.on_event("startup")
async def startup():
    asyncio.create_task(start_bot())
    print("✅ Telegram bot started")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/auth/callback")
async def auth_callback(request: Request):
    code = request.query_params.get("code")

    if not code:
        return PlainTextResponse("❌ Missing code", status_code=400)

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "offline_access Mail.Read"
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(TOKEN_URL, data=data)
        token = r.json()

    if "access_token" not in token:
        return PlainTextResponse(f"❌ Token error: {token}", status_code=400)

    # TODO: store token in DB mapped to Telegram user

    return PlainTextResponse("✅ Outlook connected successfully. You can return to Telegram.")
