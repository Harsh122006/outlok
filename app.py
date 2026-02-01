import asyncio
import json
from flask import Flask, request, jsonify
from telegram_bot import create_application, handle_auth_callback

app = Flask(__name__)

# Global Telegram application
telegram_app = None

@app.route("/")
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Telegram Outlook Bot",
        "endpoints": ["/", "/auth/callback", "/webhook"]
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
    
    if success and telegram_app:
        # Try to notify user
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
            except Exception as e:
                print(f"Failed to notify user: {e}")
        
        asyncio.create_task(send_notification())
    
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
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✅</div>
                <h1>Outlook Connected!</h1>
                <p>Your Outlook account has been successfully linked with the Telegram bot.</p>
                <p>You can now close this window and return to Telegram to start reading your emails.</p>
                <p><em>The bot will send you a confirmation message shortly.</em></p>
            </div>
            <script>
                // Auto-close after 5 seconds
                setTimeout(() => window.close(), 5000);
            </script>
        </body>
    </html>
    """

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle Telegram webhook (optional, for production)"""
    if request.is_json:
        update_data = request.get_json()
        
        async def process_update():
            update = Update.de_json(update_data, telegram_app.bot)
            await telegram_app.process_update(update)
        
        asyncio.create_task(process_update())
        return jsonify({"status": "ok"})
    
    return jsonify({"error": "Invalid data"}), 400

@app.route("/debug")
def debug():
    """Debug endpoint to see connected users"""
    from telegram_bot import user_tokens
    return jsonify({
        "connected_users": len(user_tokens),
        "users": list(user_tokens.keys())
    })

async def start_bot():
    """Start the Telegram bot"""
    global telegram_app
    
    # Create Telegram application
    telegram_app = create_application()
    
    # Initialize
    await telegram_app.initialize()
    await telegram_app.start()
    
    print("✅ Telegram bot started successfully!")
    
    # Start polling for updates
    await telegram_app.updater.start_polling()
    
    # Keep the bot running
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await telegram_app.stop()
        await telegram_app.shutdown()

def run_flask():
    """Run Flask app"""
    app.run(host="0.0.0.0", port=8080, debug=False)

async def main():
    """Main async function to run both bot and Flask"""
    # Start bot in background
    bot_task = asyncio.create_task(start_bot())
    
    # Run Flask in executor (since Flask is synchronous)
    loop = asyncio.get_event_loop()
    flask_task = loop.run_in_executor(None, run_flask)
    
    # Wait for both tasks
    await asyncio.gather(bot_task, flask_task)

if __name__ == "__main__":
    # Start the application
    asyncio.run(main())
