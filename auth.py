import secrets
import aiohttp
import logging
from datetime import datetime, timedelta
from urllib.parse import quote

logger = logging.getLogger(__name__)

# In-memory store for state verification (use Redis in production)
state_store = {}

def generate_auth_url(user_id: int, client_id: str, redirect_uri: str) -> str:
    """
    Generate Microsoft OAuth authorization URL
    """
    try:
        # Generate random state for CSRF protection
        state_token = secrets.token_urlsafe(32)
        state = f"{user_id}:{state_token}"
        
        # Store state for verification
        state_store[state] = {
            "user_id": user_id,
            "created": datetime.now(),
            "used": False
        }
        
        # Clean old states (older than 10 minutes)
        expired_keys = [
            key for key, data in state_store.items()
            if datetime.now() - data["created"] > timedelta(minutes=10)
        ]
        for key in expired_keys:
            del state_store[key]
        
        # Build authorization URL
        auth_url = (
            f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            f"&scope={quote('Mail.Read offline_access', safe='')}"
            f"&state={state}"
            f"&response_mode=query"
        )
        
        return auth_url
        
    except Exception as e:
        logger.error(f"Error generating auth URL: {e}")
        return None

async def exchange_code_for_token(code: str, client_id: str, client_secret: str, redirect_uri: str):
    """
    Exchange authorization code for access tokens
    """
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "scope": "Mail.Read offline_access"
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data, headers=headers) as response:
                if response.status == 200:
                    tokens = await response.json()
                    
                    # Calculate expiration time
                    expires_in = tokens.get('expires_in', 3600)
                    expires_at = datetime.now() + timedelta(seconds=expires_in)
                    tokens['expires_at'] = expires_at.isoformat()
                    
                    logger.info(f"Successfully obtained tokens for client {client_id}")
                    return tokens
                else:
                    error_text = await response.text()
                    logger.error(f"Token exchange failed: {response.status} - {error_text}")
                    return None
                    
    except Exception as e:
        logger.error(f"Error exchanging code for token: {e}")
        return None

async def refresh_access_token(refresh_token: str, client_id: str, client_secret: str):
    """
    Refresh expired access token
    """
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "Mail.Read offline_access"
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data, headers=headers) as response:
                if response.status == 200:
                    tokens = await response.json()
                    
                    expires_in = tokens.get('expires_in', 3600)
                    expires_at = datetime.now() + timedelta(seconds=expires_in)
                    tokens['expires_at'] = expires_at.isoformat()
                    
                    logger.info("Successfully refreshed access token")
                    return tokens
                else:
                    error_text = await response.text()
                    logger.error(f"Token refresh failed: {response.status} - {error_text}")
                    return None
                    
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        return None

def verify_state(state: str) -> int:
    """
    Verify state parameter and return user_id
    """
    try:
        if state not in state_store:
            return None
        
        state_data = state_store[state]
        
        # Check if state is expired (10 minutes)
        if datetime.now() - state_data["created"] > timedelta(minutes=10):
            del state_store[state]
            return None
        
        # Check if state was already used
        if state_data["used"]:
            return None
        
        # Mark as used and clean up
        state_data["used"] = True
        
        return state_data["user_id"]
        
    except Exception as e:
        logger.error(f"Error verifying state: {e}")
        return None
