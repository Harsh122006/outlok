#!/usr/bin/env python3
"""
Railway-ready version with health check endpoint
"""

import asyncio
import threading
from health import app as health_app
from bot import OutlookEmailWatcherBot

def run_health_check():
    """Run Flask health check server in separate thread"""
    health_app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

async def main():
    """Main function with health check"""
    # Start health check server in background thread
    health_thread = threading.Thread(target=run_health_check, daemon=True)
    health_thread.start()
    
    # Start Telegram bot
    bot = OutlookEmailWatcherBot()
    await bot.application.initialize()
    await bot.application.start()
    await bot.application.updater.start_polling()
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
