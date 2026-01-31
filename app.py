import os
import threading
import uvicorn

from health import app as health_app
from telegram_bot import run_bot


def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        health_app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    # Start Telegram bot in background
    threading.Thread(target=run_bot, daemon=True).start()

    # Start HTTP server (Railway needs this)
    start_health_server()
