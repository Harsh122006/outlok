import threading
import asyncio
from flask import Flask
from telegram_bot import run_telegram_bot

# Flask app (for Railway health check + OAuth callback)
app = Flask(__name__)

@app.route("/")
def home():
    return "OK", 200

@app.route("/auth/callback")
def auth_callback():
    return "You can close this window. Authentication successful.", 200


def run_flask():
    # Railway exposes PORT automatically
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    # 1️⃣ Start Flask in BACKGROUND
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # 2️⃣ Run Telegram bot in MAIN thread (IMPORTANT)
    asyncio.run(run_telegram_bot())
