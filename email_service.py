import requests
from datetime import datetime, timedelta
from database import Session, Email, User
from outlook_auth import OutlookAuth
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.auth = OutlookAuth()
    
    def get_valid_token(self, telegram_id: str) -> Optional[str]:
        """Get valid access token, refreshing if necessary"""
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user or not user.access_token:
            return None
        
        # Check if token needs refresh
        if datetime.utcnow() > user.expires_at:
            logger.info(f"Refreshing token for user {telegram_id}")
            result = self.auth.refresh_token(user.refresh_token)
            
            if result and 'access_token' in result:
                user.access_token = result['access_token']
                user.refresh_token = result.get('refresh_token', user.refresh_token)
                user.expires_at = datetime.utcnow() + timedelta(seconds=result.get('expires_in', 3600))
                session.commit()
                logger.info(f"Token refreshed for user {telegram_id}")
            else:
                logger.error(f"Token refresh failed for user {telegram_id}")
                return None
        
        return user.access_token
    
    def get_emails(self, telegram_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch emails from Outlook"""
        access_token = self.get_valid_token(telegram_id)
        if not access_token:
            logger.error(f"No valid token for user {telegram_id}")
            return []
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Prefer': 'outlook.body-content-type="text"'
        }
        
        try:
            # Get emails
            params = {
                '$top': limit,
                '$orderby': 'receivedDateTime desc',
                '$select': 'id,subject,sender,toRecipients,bodyPreview,receivedDateTime,hasAttachments,isRead'
            }
            
            response = requests.get(
                'https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages',
                headers=headers,
                params=params,
                timeout=30
            )
            
            response.raise_for_status()
            
            emails = response.json().get('value', [])
            
            # Store emails in database
            for email in emails:
                self.store_email(telegram_id, email)
            
            logger.info(f"Fetched {len(emails)} emails for user {telegram_id}")
            return self._format_emails(emails)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching emails for user {telegram_id}: {e}")
            return []
    
    def _format_emails(self, emails: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format emails for Telegram display"""
        formatted = []
        for email in emails:
            sender = email['sender']['emailAddress']['address']
            subject = email.get('subject', 'No Subject')[:100]
            preview = email.get('bodyPreview', '')[:150]
            date = email['receivedDateTime']
            has_attachments = email.get('hasAttachments', False)
            is_read = email.get('isRead', False)
            
            formatted.append({
                'sender': sender,
                'subject': subject,
                'preview': preview,
                'date': date,
                'has_attachments': has_attachments,
                'is_read': is_read
            })
        
        return formatted
    
    def store_email(self, telegram_id: str, email_data: Dict[str, Any]):
        """Store email in database"""
        session = Session()
        
        try:
            # Check if email already exists
            existing = session.query(Email).filter_by(outlook_id=email_data['id']).first()
            if existing:
                return
            
            # Parse received date
            received_str = email_data['receivedDateTime'].replace('Z', '+00:00')
            received_date = datetime.fromisoformat(received_str)
            
            # Create email record
            email = Email(
                telegram_id=telegram_id,
                outlook_id=email_data['id'],
                sender=email_data['sender']['emailAddress']['address'],
                recipient=telegram_id,
                subject=email_data.get('subject', 'No Subject'),
                body=email_data.get('bodyPreview', ''),
                received_at=received_date,
                has_attachments=email_data.get('hasAttachments', False),
                is_read=email_data.get('isRead', False)
            )
            
            session.add(email)
            session.commit()
            logger.info(f"Stored email {email_data['id']} for user {telegram_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing email for user {telegram_id}: {e}")
    
    def get_stored_emails(self, telegram_id: str, limit: int = 20) -> List[Email]:
        """Retrieve stored emails from database"""
        session = Session()
        try:
            emails = session.query(Email).filter_by(telegram_id=telegram_id)\
                .order_by(Email.received_at.desc())\
                .limit(limit).all()
            
            logger.info(f"Retrieved {len(emails)} stored emails for user {telegram_id}")
            return emails
            
        except Exception as e:
            logger.error(f"Error retrieving stored emails for user {telegram_id}: {e}")
            return []
    
    def search_emails(self, telegram_id: str, query: str, limit: int = 10) -> List[Email]:
        """Search emails by subject or sender"""
        session = Session()
        try:
            emails = session.query(Email).filter_by(telegram_id=telegram_id)\
                .filter((Email.subject.ilike(f'%{query}%')) | (Email.sender.ilike(f'%{query}%')))\
                .order_by(Email.received_at.desc())\
                .limit(limit).all()
            
            logger.info(f"Found {len(emails)} emails matching '{query}' for user {telegram_id}")
            return emails
            
        except Exception as e:
            logger.error(f"Error searching emails for user {telegram_id}: {e}")
            return []
