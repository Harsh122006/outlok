# app.py
import os
import requests
from fastapi import FastAPI, Request

app = FastAPI()

CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

@app.get("/auth/callback")
async def auth_callback(request: Request):
    code = request.query_params.get("code")

    if not code:
        return {"error": "Missing authorization code"}

    token_response = requests.post(
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "scope": "offline_access Mail.Read",
        },
        timeout=10,
    )

    if token_response.status_code != 200:
        return {
            "error": "Token exchange failed",
            "details": token_response.text,
        }

    tokens = token_response.json()

    # TODO: save tokens linked to Telegram user
    return {
        "success": True,
        "message": "Outlook connected. You can return to Telegram.",
    }
