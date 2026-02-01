import os
import requests
from flask import Flask, request

app = Flask(__name__)

# Get environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

@app.route('/')
def home():
    return "✅ Outlook Auth Callback Server is running"

@app.route('/auth/callback')
def auth_callback():
    """Handle Microsoft OAuth callback"""
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code or not state:
        return "❌ Missing parameters", 400
    
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
    
    try:
        response = requests.post(token_url, data=data, timeout=10)
        if response.status_code == 200:
            tokens = response.json()
            # Here you would save tokens to database
            # For now, just show success
            
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>✅ Connected!</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        text-align: center;
                        padding: 50px;
                        background: #f0f2f5;
                    }
                    .success {
                        color: green;
                        font-size: 48px;
                    }
                    .container {
                        max-width: 500px;
                        margin: 0 auto;
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success">✅</div>
                    <h1>Outlook Connected!</h1>
                    <p>Your Outlook account has been successfully linked.</p>
                    <p>You can close this window and return to Telegram.</p>
                </div>
                <script>
                    setTimeout(() => window.close(), 3000);
                </script>
            </body>
            </html>
            '''
        else:
            return f"❌ Token exchange failed: {response.text}", 400
            
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
