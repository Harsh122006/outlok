import threading
from flask import Flask
from telegram_bot import start_telegram_bot
import os

app = Flask(__name__)


@app.route("/")
def home():
    return "OK", 200


@app.route("/auth/callback")
def auth_callback():
    return "Authentication successful. You can close this tab.", 200


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    # Flask in background
    threading.Thread(target=run_flask, daemon=True).start()

    # Telegram bot in MAIN thread
    start_telegram_bot()
