import msal
import requests
from datetime import datetime, timedelta
import os
import secrets
import hashlib
import json
import base64
from database import Session, User
from typing import Optional, Dict, Any

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
        
        # In-memory cache for auth states (use Redis in production)
        self.auth_states = {}
    
    def get_auth_url(self, telegram_id: str) -> str:
        """Generate UNIQUE Outlook authentication URL each time"""
        # Generate unique state
        state = secrets.token_urlsafe(32)
        
        # Generate PKCE code verifier and challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge).decode().replace('=', '')
        
        # Store state and code verifier
        self.auth_states[state] = {
            'telegram_id': telegram_id,
            'code_verifier': code_verifier,
            'created_at': datetime.utcnow(),
            'used': False
        }
        
        # Clean up old states
        self._clean_old_states()
        
        # Generate auth URL with unique parameters
        auth_url = self.app.get_authorization_request_url(
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method='S256'
        )
        
        return auth_url
    
    def _clean_old_states(self):
        """Remove states older than 10 minutes"""
        current_time = datetime.utcnow()
        expired_states = []
        
        for state, data in self.auth_states.items():
            if current_time - data['created_at'] > timedelta(minutes=10):
                expired_states.append(state)
        
        for state in expired_states:
            del self.auth_states[state]
    
    def get_token_from_code(self, code: str, state: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for tokens"""
        try:
            # Verify state exists and is valid
            if state not in self.auth_states:
                return None
            
            state_data = self.auth_states[state]
            
            # Check if state was already used
            if state_data['used']:
                return None
            
            # Mark as used
            self.auth_states[state]['used'] = True
            
            # Exchange code for token with PKCE
            result = self.app.acquire_token_by_authorization_code(
                code,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri,
                code_verifier=state_data['code_verifier']
            )
            
            # Remove state after use
            del self.auth_states[state]
            
            return result
            
        except Exception as e:
            print(f"❌ Token exchange error: {e}")
            return None
    
    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user email from Microsoft Graph"""
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(
                'https://graph.microsoft.com/v1.0/me',
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error getting user info: {e}")
            return {}
    
    def refresh_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh access token"""
        try:
            result = self.app.acquire_token_by_refresh_token(
                refresh_token,
                scopes=self.scopes
            )
            return result
        except Exception as e:
            print(f"❌ Token refresh error: {e}")
            return None
    
    def validate_state(self, state: str, telegram_id: str) -> bool:
        """Validate if state belongs to user"""
        if state not in self.auth_states:
            return False
        
        state_data = self.auth_states[state]
        
        # Check if state matches telegram_id and not expired
        if (state_data['telegram_id'] == telegram_id and 
            not state_data['used'] and
            datetime.utcnow() - state_data['created_at'] < timedelta(minutes=10)):
            return True
        
        return False
