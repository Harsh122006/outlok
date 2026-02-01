import requests
from datetime import datetime, timedelta
from database import Session, Email, User
from outlook_auth import OutlookAuth

class EmailService:
    def __init__(self):
        self.auth = OutlookAuth()
    
    def get_valid_token(self, telegram_id):
        """Get valid access token, refreshing if necessary"""
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user or not user.access_token:
            return None
        
        # Check if token needs refresh
        if datetime.utcnow() > user.expires_at:
            result = self.auth.refresh_token(user.refresh_token)
            if 'access_token' in result:
                user.access_token = result['access_token']
                user.refresh_token = result.get('refresh_token', user.refresh_token)
                user.expires_at = datetime.utcnow() + timedelta(seconds=result['expires_in'])
                session.commit()
        
        return user.access_token
    
    def get_emails(self, telegram_id, limit=10):
        """Fetch emails from Outlook"""
        access_token = self.get_valid_token(telegram_id)
        if not access_token:
            return []
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Prefer': 'outlook.body-content-type="text"'
        }
        
        # Get emails
        params = {
            '$top': limit,
            '$orderby': 'receivedDateTime desc',
            '$select': 'id,subject,sender,toRecipients,bodyPreview,receivedDateTime,hasAttachments'
        }
        
        response = requests.get(
            'https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages',
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            emails = response.json().get('value', [])
            return self._format_emails(emails)
        
        return []
    
    def _format_emails(self, emails):
        """Format emails for Telegram display"""
        formatted = []
        for email in emails:
            sender = email['sender']['emailAddress']['address']
            subject = email.get('subject', 'No Subject')
            preview = email.get('bodyPreview', '')[:100]
            date = email['receivedDateTime']
            has_attachments = email.get('hasAttachments', False)
            
            formatted.append({
                'sender': sender,
                'subject': subject,
                'preview': preview,
                'date': date,
                'has_attachments': has_attachments
            })
        
        return formatted
    
    def store_email(self, telegram_id, email_data):
        """Store email in database"""
        session = Session()
        
        # Check if email already exists
        existing = session.query(Email).filter_by(outlook_id=email_data['id']).first()
        if not existing:
            email = Email(
                telegram_id=telegram_id,
                outlook_id=email_data['id'],
                sender=email_data['sender']['emailAddress']['address'],
                recipient=telegram_id,
                subject=email_data.get('subject', 'No Subject'),
                body=email_data.get('body', {}).get('content', ''),
                received_at=datetime.fromisoformat(email_data['receivedDateTime'].replace('Z', '+00:00')),
                has_attachments=email_data.get('hasAttachments', False)
            )
            session.add(email)
            session.commit()
    
    def get_stored_emails(self, telegram_id, limit=20):
        """Retrieve stored emails from database"""
        session = Session()
        emails = session.query(Email).filter_by(telegram_id=telegram_id)\
            .order_by(Email.received_at.desc())\
            .limit(limit).all()
        
        return emails
