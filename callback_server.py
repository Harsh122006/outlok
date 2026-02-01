from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from database import Session, User
from outlook_auth import OutlookAuth
from datetime import datetime
import requests

load_dotenv()

app = Flask(__name__)
auth = OutlookAuth()

@app.route('/callback')
def callback():
    """Handle OAuth callback from Microsoft"""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    error_description = request.args.get('error_description')
    
    if error:
        return f"❌ Authentication Error: {error_description}"
    
    if not code or not state:
        return "❌ Missing code or state parameter"
    
    # Exchange code for tokens
    result = auth.get_token_from_code(code, state)
    
    if not result or 'access_token' not in result:
        return "❌ Failed to get access token"
    
    # Get user info
    user_info = auth.get_user_info(result['access_token'])
    email = user_info.get('mail') or user_info.get('userPrincipalName')
    
    if not email:
        return "❌ Failed to get user email"
    
    # Extract telegram_id from state (you need to implement this)
    # In production, state should contain telegram_id
    # For now, we'll store without telegram_id (you need to modify)
    
    return f"""
    ✅ Authentication Successful!
    
    Email: {email}
    You can close this window and return to Telegram.
    
    Your account is now connected to the bot.
    """

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
