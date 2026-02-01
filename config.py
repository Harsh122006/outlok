import os

# Telegram
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Microsoft
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")

# Webhook
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL")
REDIRECT_URI = f"{WEBHOOK_URL}/auth/callback" if WEBHOOK_URL else "http://localhost:8080/auth/callback"

# In-memory storage (for demo - use DB in production)
user_tokens = {}
