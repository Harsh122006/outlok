import asyncio
import threading
import logging
from flask import Flask, request, jsonify
from telegram_bot import create_application, handle_auth_callback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global Telegram application instance
telegram_app = None
bot_thread = None

@app.route("/")
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Telegram Outlook Bot",
        "endpoints": ["/", "/auth/callback"]
    })

@app.route("/auth/callback")
def auth_callback():
    """Handle Microsoft OAuth callback"""
    code = request.args.get("code")
    state = request.args.get("state")
    
    if not code or not state:
        return """
        <html>
            <body>
                <h2>❌ Authorization Failed</h2>
                <p>Missing code or state parameter.</p>
                <p>Return to Telegram and try /connect again.</p>
            </body>
        </html>
        """, 400
    
    # Handle the auth callback
    user_id, success = handle_auth_callback(code, state)
    
    if success:
        # Try to notify user (async)
        async def send_notification():
            try:
                await telegram_app.bot.send_message(
                    chat_id=user_id,
                    text="✅ *Outlook Connected Successfully!*\n\n"
                         "You can now use:\n"
                         "• /inbox - Read latest emails\n"
                         "• /unread - Show unread emails\n\n"
                         "Happy email reading! 📧",
                    parse_mode='Markdown'
                )
                logger.info(f"Sent connection confirmation to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
        
        # Run notification in background
        if telegram_app:
            asyncio.run_coroutine_threadsafe(send_notification(), telegram_app.bot._loop)
    
    # Return success page
    return """
    <html>
        <head>
            <title>Outlook Connected</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 50px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    min-height: 100vh;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }
                .container {
                    background: rgba(255, 255, 255, 0.1);
                    padding: 40px;
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                    max-width: 500px;
                }
                h1 { font-size: 2.5em; margin-bottom: 20px; }
                p { font-size: 1.2em; line-height: 1.6; opacity: 0.9; }
                .success { color: #4CAF50; font-size: 4em; }
                .button {
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: white;
                    color: #667eea;
                    text-decoration: none;
                    border-radius: 5px;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✅</div>
                <h1>Outlook Connected!</h1>
                <p>Your Outlook account has been successfully linked with the Telegram bot.</p>
                <p>You can now close this window and return to Telegram.</p>
                <a href="https://t.me/" class="button">Return to Telegram</a>
            </div>
            <script>
                // Auto-close after 3 seconds
                setTimeout(() => window.close(), 3000);
            </script>
        </body>
    </html>
    """

@app.route("/debug")
def debug():
    """Debug endpoint to see connected users"""
    from telegram_bot import user_tokens
    return jsonify({
        "connected_users": len(user_tokens),
        "users": list(user_tokens.keys()),
        "bot_running": telegram_app is not None
    })

def run_bot():
    """Run Telegram bot in a separate thread"""
    global telegram_app
    
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Create and start Telegram application
        telegram_app = create_application()
        
        # Run bot with polling
        loop.run_until_complete(telegram_app.initialize())
        loop.run_until_complete(telegram_app.start())
        loop.run_until_complete(telegram_app.updater.start_polling())
        
        logger.info("✅ Telegram bot started successfully!")
        
        # Keep the event loop running
        loop.run_forever()
        
    except Exception as e:
        logger.error(f"Bot thread error: {e}")
    finally:
        if telegram_app:
            loop.run_until_complete(telegram_app.stop())
            loop.run_until_complete(telegram_app.shutdown())
        loop.close()

def start_bot_thread():
    """Start bot in a separate thread"""
    global bot_thread
    if bot_thread and bot_thread.is_alive():
        logger.warning("Bot thread is already running")
        return
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Bot thread started")

# Start bot thread when Flask app starts
@app.before_first_request
def initialize():
    """Initialize bot thread before first request"""
    start_bot_thread()

# Production WSGI entry point
def create_app():
    """Create Flask app for production WSGI servers"""
    return app

# Development server (for testing only)
if __name__ == "__main__":
    logger.info("Starting Flask development server...")
    
    # Start bot thread
    start_bot_thread()
    
    # Run Flask with production settings
    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', 8080, app, use_reloader=False, use_debugger=False)
