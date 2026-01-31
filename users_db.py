import json
import os
import logging
from typing import Dict, Optional, Tuple
from cryptography.fernet import Fernet
import base64
import hashlib

logger = logging.getLogger(__name__)

class UserDatabase:
    def __init__(self, db_file: str = 'users_db.json'):
        self.db_file = db_file
        self.encryption_key = self.get_encryption_key()
        self.cipher = Fernet(self.encryption_key)
        
        # Load or create database
        self.users = self.load_database()
    
    def get_encryption_key(self) -> bytes:
        """Get or generate encryption key"""
        key_env = os.getenv('ENCRYPTION_KEY')
        if key_env:
            # Use key from environment
            key_bytes = key_env.encode()
            if len(key_bytes) < 32:
                # Pad if necessary
                key_bytes = key_bytes.ljust(32, b'0')
            return base64.urlsafe_b64encode(key_bytes[:32])
        else:
            # Generate key from bot token (for Railway)
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN', 'default_token')
            key = hashlib.sha256(bot_token.encode()).digest()
            return base64.urlsafe_b64encode(key[:32])
    
    def encrypt_data(self, data: str) -> str:
        """Encrypt sensitive data"""
        encrypted = self.cipher.encrypt(data.encode())
        return encrypted.decode()
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        decrypted = self.cipher.decrypt(encrypted_data.encode())
        return decrypted.decode()
    
    def load_database(self) -> Dict:
        """Load database from file"""
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Could not load database: {e}")
        
        return {}
    
    def save_database(self):
        """Save database to file"""
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.users, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save database: {e}")
    
    def save_user(self, user_id: int, email: str, password: str):
        """Save user credentials to database"""
        try:
            encrypted_email = self.encrypt_data(email)
            encrypted_password = self.encrypt_data(password)
            
            self.users[str(user_id)] = {
                'email': encrypted_email,
                'password': encrypted_password,
                'created_at': os.getenv('RAILWAY_SNAPSHOT_ID', 'local'),
                'updated_at': os.getenv('RAILWAY_SNAPSHOT_ID', 'local')
            }
            
            self.save_database()
            logger.info(f"Saved user {user_id} to database")
            
        except Exception as e:
            logger.error(f"Error saving user {user_id}: {e}")
            raise
    
    def get_user(self, user_id: int) -> Optional[Tuple[str, str]]:
        """Get user credentials"""
        try:
            user_data = self.users.get(str(user_id))
            if user_data:
                email = self.decrypt_data(user_data['email'])
                password = self.decrypt_data(user_data['password'])
                return email, password
        except Exception as e:
            logger.error(f"Error retrieving user {user_id}: {e}")
        
        return None
    
    def user_exists(self, user_id: int) -> bool:
        """Check if user exists in database"""
        return str(user_id) in self.users
    
    def delete_user(self, user_id: int):
        """Delete user from database"""
        try:
            if str(user_id) in self.users:
                del self.users[str(user_id)]
                self.save_database()
                
                # Also delete state file
                state_file = f'user_{user_id}_state.json'
                if os.path.exists(state_file):
                    os.remove(state_file)
                
                logger.info(f"Deleted user {user_id} from database")
                return True
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
        
        return False
    
    def get_all_users(self) -> Dict:
        """Get all users (for admin purposes)"""
        return {uid: data for uid, data in self.users.items()}
