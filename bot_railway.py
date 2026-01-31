#!/usr/bin/env python3
"""
Railway-ready Telegram bot with optional health check
"""

import os
import asyncio
import threading
from telegram.ext import Application
from bot import OutlookEmailWatcherBot
from health import app as health_app


def run_health_check():
    """Run Flask health check server"""
    health_app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        debug=False,
        use_reloader=False,
    )


async def post_init(application: Application):
    """
    Runs AFTER the Telegram event loop is ready.
    Start background tasks here if needed.
    """
    # If your OutlookEmailWatcherBot starts background jobs,
    # they should be started here.
    pass


def main():
    # Start health check in background (optional)
    threading.Thread(target=run_health_check, daemon=True).start()

    # Create your bot
    bot = OutlookEmailWatcherBot()

    # Attach post-init hook
    bot.application.post_init = post_init

    print("Bot running on Railway...")

    # This blocks forever (correct)
    bot.application.run_polling(
        allowed_updates=None,
        close_loop=False
    )


if __name__ == "__main__":
    main()
