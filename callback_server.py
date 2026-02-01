from flask import Flask, request, redirect
import os
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

app = Flask(__name__)

@app.route('/callback')
def callback():
    """Handle OAuth callback from Microsoft"""
    code = request.args.get('code')
    state = request.args.get('state')  # Telegram ID
    
    if code and state:
        # Encode parameters for Telegram deep linking
        encoded_code = urllib.parse.quote(code)
        
        # Redirect back to bot with auth code
        bot_url = f"https://t.me/your_bot_username?start=auth_{encoded_code}"
        return redirect(bot_url)
    
    return "Authentication failed. Please try again."

if __name__ == "__main__":
    app.run(port=8000)
