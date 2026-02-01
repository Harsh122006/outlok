import msal
import requests
from datetime import datetime, timedelta
import os
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
        """Generate Outlook authentication URL"""
        auth_url = self.app.get_authorization_request_url(
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
            state=telegram_id
        )
        return auth_url
    
    def get_token_from_code(self, code):
        """Exchange authorization code for tokens"""
        result = self.app.acquire_token_by_authorization_code(
            code,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        return result
    
    def get_user_info(self, access_token):
        """Get user email from Microsoft Graph"""
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(
            'https://graph.microsoft.com/v1.0/me',
            headers=headers
        )
        return response.json()
    
    def refresh_token(self, refresh_token):
        """Refresh access token"""
        result = self.app.acquire_token_by_refresh_token(
            refresh_token,
            scopes=self.scopes
        )
        return result
