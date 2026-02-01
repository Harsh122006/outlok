import os
from flask import Flask, request
import requests
from bot import user_tokens  # Import from bot module

app = Flask(__name__)

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

@app.route('/')
def home():
    return "✅ Outlook Callback Server"

@app.route('/auth/callback')
def auth_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code or not state:
        return "Missing parameters", 400
    
    try:
        user_id = int(state)
        
        # Exchange code for tokens
        token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "scope": "Mail.Read offline_access"
        }
        
        response = requests.post(token_url, data=data, timeout=10)
        if response.status_code == 200:
            tokens = response.json()
            
            # Store in bot's user_tokens dictionary
            from datetime import datetime, timedelta
            tokens['expires_at'] = datetime.now() + timedelta(seconds=tokens.get('expires_in', 3600))
            user_tokens[user_id] = tokens
            
            return '''
            <html>
            <body style="text-align:center;padding:50px;">
                <h1 style="color:green;">✅ Connected!</h1>
                <p>Outlook account linked successfully!</p>
                <p>Return to Telegram and use /inbox to read emails.</p>
                <script>setTimeout(() => window.close(), 3000)</script>
            </body>
            </html>
            '''
        else:
            return f"Token exchange failed: {response.text}", 400
            
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
