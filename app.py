import asyncio
import logging
from flask import Flask, request, jsonify
import config
from telegram_bot import create_application, handle_auth_callback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize Telegram bot
telegram_app = create_application()

# ==================== FLASK ROUTES ====================

@app.route("/")
def health():
    """Health check"""
    return jsonify({
        "status": "online",
        "service": "Telegram Outlook Bot",
        "webhook": f"{config.WEBHOOK_URL}/webhook" if config.WEBHOOK_URL else "Not set",
        "connected_users": len(config.user_tokens)
    })

@app.route("/auth/callback")
def auth_callback():
    """Handle Microsoft OAuth callback"""
    code = request.args.get("code")
    state = request.args.get("state")
    
    if not code or not state:
        return "Missing parameters", 400
    
    user_id, success = handle_auth_callback(code, state)
    
    # Notify user in Telegram
    async def send_notification():
        try:
            await telegram_app.bot.send_message(
                chat_id=user_id,
                text="✅ *Outlook Connected!*\n\nUse /inbox to read your emails.",
                parse_mode='Markdown'
            )
            logger.info(f"Notified user {user_id}")
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")
    
    if success and user_id:
        asyncio.run(send_notification())
    
    # Return HTML page
    return """
    <!DOCTYPE html>
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
                margin: 0;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                max-width: 500px;
            }
            h1 {
                font-size: 2.5em;
                margin-bottom: 20px;
            }
            p {
                font-size: 1.2em;
                line-height: 1.6;
                opacity: 0.9;
            }
            .success {
                color: #4CAF50;
                font-size: 4em;
                margin-bottom: 20px;
            }
            .button {
                display: inline-block;
                margin-top: 20px;
                padding: 12px 24px;
                background: white;
                color: #667eea;
                text-decoration: none;
                border-radius: 8px;
                font-weight: bold;
                border: none;
                cursor: pointer;
                font-size: 1em;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success">✅</div>
            <h1>Successfully Connected!</h1>
            <p>Your Outlook account is now linked with the Telegram bot.</p>
            <p>You can close this window and return to Telegram.</p>
            <button onclick="window.close()" class="button">Close Window</button>
        </div>
        <script>
            // Auto-close after 3 seconds
            setTimeout(() => {
                window.close();
            }, 3000);
        </script>
    </body>
    </html>
    """

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle Telegram webhook updates"""
    if request.is_json:
        update_data = request.get_json()
        
        async def process_update():
            from telegram import Update
            update = Update.de_json(update_data, telegram_app.bot)
            await telegram_app.process_update(update)
        
        # Process update in background
        asyncio.run(process_update())
        
    return jsonify({"status": "ok"})

@app.route("/set-webhook", methods=["GET", "POST"])
async def set_webhook():
    """Set Telegram webhook (call this once after deployment)"""
    if not config.WEBHOOK_URL:
        return jsonify({"error": "WEBHOOK_URL not set"}), 400
    
    webhook_url = f"{config.WEBHOOK_URL}/webhook"
    
    try:
        # Initialize the application
        await telegram_app.initialize()
        
        # Set webhook
        result = await telegram_app.bot.set_webhook(webhook_url)
        
        # Start the application
        await telegram_app.start()
        
        return jsonify({
            "success": result,
            "webhook_url": webhook_url,
            "bot_username": (await telegram_app.bot.get_me()).username
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/debug")
def debug():
    """Debug info"""
    return jsonify({
        "connected_users": list(config.user_tokens.keys()),
        "total_users": len(config.user_tokens),
        "webhook_url": f"{config.WEBHOOK_URL}/webhook" if config.WEBHOOK_URL else None,
        "redirect_uri": config.REDIRECT_URI
    })

# ==================== STARTUP ====================

@app.before_request
def initialize_bot():
    """Initialize bot on first request"""
    if not hasattr(app, 'bot_initialized'):
        async def init():
            await telegram_app.initialize()
            await telegram_app.start()
            
            # Set webhook if URL is configured
            if config.WEBHOOK_URL:
                webhook_url = f"{config.WEBHOOK_URL}/webhook"
                await telegram_app.bot.set_webhook(webhook_url)
                logger.info(f"Webhook set to: {webhook_url}")
        
        asyncio.run(init())
        app.bot_initialized = True

# ==================== MAIN ====================

if __name__ == "__main__":
    # Run Flask app
    app.run(host="0.0.0.0", port=8080, debug=False)
