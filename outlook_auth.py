import msal
import requests
from datetime import datetime, timedelta
import os
import secrets
import hashlib
import json
from database import Session, User
import urllib.parse

class OutlookAuth:
    def __init__(self):
        self.client_id = os.getenv('OUTLOOK_CLIENT_ID')
        self.client_secret = os.getenv('OUTLOOK_CLIENT_SECRET')
        self.tenant_id = os.getenv('OUTLOOK_TENANT_ID')
        self.redirect_uri = os.getenv('OUTLOOK_REDIRECT_URI')
        self.scopes = ['User.Read', 'Mail.Read', 'Mail.Send', 'offline_access']
        
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret
        )
    
    def get_auth_url(self, telegram_id):
        """Generate UNIQUE Outlook authentication URL"""
        # Generate unique state with timestamp and random token
        timestamp = int(datetime.utcnow().timestamp())
        random_token = secrets.token_urlsafe(16)
        
        # Create state object
        state_data = {
            'telegram_id': telegram_id,
            'timestamp': timestamp,
            'random': random_token,
            'nonce': secrets.token_urlsafe(8)
        }
        
        # Convert state to string
        state_str = json.dumps(state_data)
        
        # Generate code verifier and challenge (PKCE)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge).decode().replace('=', '')
        
        # Store code verifier temporarily (you'll need a cache/store)
        self.store_code_verifier(telegram_id, code_verifier, state_str)
        
        auth_url = self.app.get_authorization_request_url(
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
            state=state_str,
            code_challenge=code_challenge,
            code_challenge_method='S256'
        )
        
        return auth_url
    
    def store_code_verifier(self, telegram_id, code_verifier, state):
        """Store code verifier temporarily (use database or cache)"""
        session = Session()
        
        # Update or create user with auth state
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id)
            session.add(user)
        
        # Store in a temporary field (you might need to add this to User model)
        # Or use a separate auth_states table
        user.auth_state = state
        user.code_verifier = code_verifier
        user.auth_requested_at = datetime.utcnow()
        
        session.commit()
    
    def get_token_from_code(self, code, state):
        """Exchange authorization code for tokens with PKCE"""
        try:
            # Parse state to get telegram_id
            state_data = json.loads(state)
            telegram_id = state_data['telegram_id']
            
            # Get stored code verifier
            session = Session()
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            
            if not user or not user.code_verifier:
                return None
            
            result = self.app.acquire_token_by_authorization_code(
                code,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri,
                code_verifier=user.code_verifier
            )
            
            # Clean up code verifier after use
            user.code_verifier = None
            user.auth_state = None
            session.commit()
            
            return result
            
        except Exception as e:
            print(f"Token exchange error: {e}")
            return None
    
    # ... rest of the methods remain the same
