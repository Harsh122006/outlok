import imaplib
import email
import json
import logging
import re
import time
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Dict, List, Optional, Tuple
import os

logger = logging.getLogger(__name__)

class EmailMonitor:
    def __init__(self, user_id: int, email: str, password: str):
        self.user_id = user_id
        self.email = email
        self.password = password
        
        # IMAP configuration
        self.imap_server = os.getenv('IMAP_SERVER', 'outlook.office365.com')
        self.imap_port = int(os.getenv('IMAP_PORT', 993))
        
        # State
        self.state_file = f'user_{user_id}_state.json'
        self.state = self.load_state()
        self.last_check = None
        
        logger.info(f"EmailMonitor initialized for user {user_id}")
    
    def load_state(self) -> Dict:
        """Load user state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load state for user {self.user_id}: {e}")
        
        return {
            'last_uid': 0,
            'processed_uids': [],
            'total_emails': 0,
            'last_email_time': None
        }
    
    def save_state(self):
        """Save user state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save state for user {self.user_id}: {e}")
    
    def test_connection(self) -> bool:
        """Test IMAP connection with provided credentials"""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email, self.password)
            mail.select('INBOX')
            mail.logout()
            logger.info(f"Connection test successful for {self.email}")
            return True
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP authentication failed for {self.email}: {e}")
            return False
        except Exception as e:
            logger.error(f"Connection test failed for {self.email}: {e}")
            return False
    
    def check_new_emails(self) -> List[Dict]:
        """Check for new emails and return list of new email data"""
        new_emails = []
        
        try:
            # Connect to IMAP
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email, self.password)
            mail.select('INBOX')
            
            # Get all UIDs
            status, data = mail.uid('search', None, 'ALL')
            if status != 'OK' or not data[0]:
                return new_emails
            
            all_uids = [int(uid) for uid in data[0].split()]
            last_uid = self.state.get('last_uid', 0)
            
            # Find new UIDs
            new_uids = [uid for uid in all_uids if uid > last_uid]
            
            if new_uids:
                logger.info(f"Found {len(new_uids)} new emails for user {self.user_id}")
                
                # Process new emails
                for uid in sorted(new_uids):
                    try:
                        email_data = self.fetch_email(mail, uid)
                        if email_data:
                            new_emails.append(email_data)
                            self.state['processed_uids'].append(uid)
                    except Exception as e:
                        logger.error(f"Error processing email {uid} for user {self.user_id}: {e}")
                
                # Update last UID
                if new_uids:
                    self.state['last_uid'] = max(new_uids)
                    self.state['total_emails'] += len(new_uids)
                    self.state['last_email_time'] = datetime.now().isoformat()
                    self.save_state()
            
            # Clean up processed UIDs list (keep last 1000)
            if len(self.state['processed_uids']) > 1000:
                self.state['processed_uids'] = self.state['processed_uids'][-1000:]
            
            mail.logout()
            
        except Exception as e:
            logger.error(f"Error checking emails for user {self.user_id}: {e}")
        
        self.last_check = datetime.now()
        return new_emails
    
    def fetch_email(self, mail: imaplib.IMAP4_SSL, uid: int) -> Optional[Dict]:
        """Fetch and parse a single email"""
        try:
            status, data = mail.uid('fetch', str(uid).encode(), '(RFC822)')
            if status != 'OK' or not data[0]:
                return None
            
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            return self.parse_email(msg)
            
        except Exception as e:
            logger.error(f"Error fetching email {uid}: {e}")
            return None
    
    def parse_email(self, msg: email.message.Message) -> Dict:
        """Parse email content"""
        email_data = {
            'uid': None,
            'subject': 'No Subject',
            'from_name': 'Unknown',
            'from_email': 'unknown@example.com',
            'date': 'Unknown',
            'preview': '',
            'attachments': [],
            'has_attachments': False
        }
        
        try:
            # Parse subject
            subject_header = msg.get('Subject', '')
            if subject_header:
                subject, encoding = decode_header(subject_header)[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else 'utf-8')
                email_data['subject'] = subject.strip()
            
            # Parse sender
            from_header = msg.get('From', '')
            name, email_addr = self.parse_sender(from_header)
            email_data['from_name'] = name
            email_data['from_email'] = email_addr
            
            # Parse date
            email_data['date'] = msg.get('Date', 'Unknown')
            
            # Parse body and attachments
            email_data['preview'], email_data['attachments'] = self.extract_content(msg)
            email_data['has_attachments'] = len(email_data['attachments']) > 0
            
        except Exception as e:
            logger.error(f"Error parsing email: {e}")
        
        return email_data
    
    def parse_sender(self, from_header: str) -> Tuple[str, str]:
        """Extract name and email from From header"""
        try:
            # Pattern: "Name <email@domain.com>"
            match = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>$', from_header)
            if match:
                return match.group(1).strip(), match.group(2).strip()
            
            # Pattern: email@domain.com
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', from_header)
            if email_match:
                return from_header, email_match.group(1)
            
        except Exception:
            pass
        
        return from_header or 'Unknown', from_header or 'unknown@example.com'
    
    def extract_content(self, msg: email.message.Message) -> Tuple[str, List[str]]:
        """Extract text preview and attachment names"""
        preview = ""
        attachments = []
        
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    
                    # Skip multipart containers
                    if content_type in ["multipart/alternative", "multipart/mixed", "multipart/related"]:
                        continue
                    
                    # Check for attachments
                    if "attachment" in content_disposition.lower():
                        filename = part.get_filename()
                        if filename:
                            attachments.append(filename)
                        continue
                    
                    # Get text preview
                    if content_type == "text/plain" and not preview:
                        try:
                            payload = part.get_payload(decode=True)
                            charset = part.get_content_charset() or 'utf-8'
                            preview = payload.decode(charset, errors='ignore')
                            preview = re.sub(r'\s+', ' ', preview).strip()
                        except:
                            pass
            else:
                # Simple email
                try:
                    payload = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or 'utf-8'
                    preview = payload.decode(charset, errors='ignore')
                    preview = re.sub(r'\s+', ' ', preview).strip()
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error extracting email content: {e}")
        
        return preview[:500], attachments
    
    def get_status(self) -> str:
        """Get monitoring status string"""
        last_check = self.last_check.strftime('%Y-%m-%d %H:%M:%S') if self.last_check else 'Never'
        last_email = self.state.get('last_email_time', 'Never')
        
        if last_email != 'Never':
            try:
                last_email_dt = datetime.fromisoformat(last_email)
                last_email = last_email_dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass
        
        return f"""
📧 <b>Account:</b> {self.email}
📊 <b>Total emails processed:</b> {self.state.get('total_emails', 0)}
⏱️ <b>Last check:</b> {last_check}
📬 <b>Last email received:</b> {last_email}
🔄 <b>Check interval:</b> Every 30 minutes
"""
