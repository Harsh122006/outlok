#!/usr/bin/env python3
"""
Outlook Email to Telegram Notifier Bot
Deployed on Railway with IMAP protocol
"""

import os
import imaplib
import email
import time
import json
import logging
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from datetime import datetime
import re
import sys
import requests
from typing import Optional, Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class OutlookTelegramNotifier:
    def __init__(self):
        """Initialize the bot with environment variables"""
        # Load configuration from environment variables
        self.email_address = os.getenv('OUTLOOK_EMAIL')
        self.password = os.getenv('OUTLOOK_PASSWORD')
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # IMAP Configuration for Outlook/Office365
        self.imap_server = os.getenv('IMAP_SERVER', 'outlook.office365.com')
        self.imap_port = int(os.getenv('IMAP_PORT', 993))
        
        # Check interval in seconds (30 minutes = 1800 seconds)
        self.check_interval = int(os.getenv('CHECK_INTERVAL_SECONDS', 1800))
        
        # State file to store last checked UID
        self.state_file = 'email_state.json'
        
        # Validate configuration
        self.validate_config()
        
        # Initialize state
        self.state = self.load_state()
        
        # Last notification time for rate limiting
        self.last_notification_time = None
        
        logger.info("Outlook Telegram Notifier initialized")
        logger.info(f"Monitoring: {self.email_address}")
        logger.info(f"Check interval: {self.check_interval} seconds")
    
    def validate_config(self):
        """Validate all required environment variables"""
        required_vars = {
            'OUTLOOK_EMAIL': self.email_address,
            'OUTLOOK_PASSWORD': self.password,
            'TELEGRAM_BOT_TOKEN': self.telegram_token,
            'TELEGRAM_CHAT_ID': self.chat_id
        }
        
        missing = [var for var, val in required_vars.items() if not val]
        if missing:
            logger.error(f"Missing required environment variables: {', '.join(missing)}")
            logger.error("Please set these in Railway environment variables")
            sys.exit(1)
    
    def load_state(self) -> Dict:
        """Load bot state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load state file: {e}")
        
        # Default state
        return {
            'last_uid': 0,
            'last_check': None,
            'processed_emails': []
        }
    
    def save_state(self):
        """Save bot state to file"""
        try:
            self.state['last_check'] = datetime.now().isoformat()
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save state: {e}")
    
    def connect_imap(self) -> Optional[imaplib.IMAP4_SSL]:
        """Establish IMAP connection to Outlook"""
        try:
            logger.info(f"Connecting to {self.imap_server}:{self.imap_port}")
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.password)
            mail.select('INBOX')
            logger.info("IMAP connection established successfully")
            return mail
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP authentication failed: {e}")
            logger.info("Note: If you have 2FA enabled, use an app password")
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
        return None
    
    def get_latest_uids(self, mail, count=10) -> List[int]:
        """Get latest email UIDs from inbox"""
        try:
            # Search for all emails, sorted by date
            status, data = mail.uid('search', None, 'ALL')
            if status == 'OK' and data[0]:
                uids = [int(uid) for uid in data[0].split()]
                # Return latest UIDs (newest first)
                return sorted(uids, reverse=True)[:count]
        except Exception as e:
            logger.error(f"Error fetching UIDs: {e}")
        return []
    
    def fetch_email(self, mail, uid: int) -> Optional[email.message.Message]:
        """Fetch email by UID"""
        try:
            status, data = mail.uid('fetch', str(uid).encode(), '(RFC822)')
            if status == 'OK' and data[0]:
                raw_email = data[0][1]
                return email.message_from_bytes(raw_email)
        except Exception as e:
            logger.error(f"Error fetching email {uid}: {e}")
        return None
    
    def parse_email(self, msg: email.message.Message) -> Dict:
        """Parse email content into structured format"""
        email_data = {
            'subject': 'No Subject',
            'from_name': 'Unknown',
            'from_email': 'unknown@example.com',
            'date': 'Unknown',
            'body': '',
            'has_attachments': False,
            'attachments': []
        }
        
        try:
            # Parse subject
            subject, encoding = decode_header(msg.get('Subject', ''))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else 'utf-8')
            email_data['subject'] = subject.strip() or 'No Subject'
            
            # Parse sender
            from_header = msg.get('From', '')
            name, email_addr = self.parse_sender(from_header)
            email_data['from_name'] = name
            email_data['from_email'] = email_addr
            
            # Parse date
            email_data['date'] = msg.get('Date', 'Unknown')
            
            # Parse body and check for attachments
            email_data['body'], email_data['has_attachments'], email_data['attachments'] = \
                self.extract_email_content(msg)
                
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
    
    def extract_email_content(self, msg) -> Tuple[str, bool, List]:
        """Extract text body and attachment info from email"""
        body = ""
        has_attachments = False
        attachments = []
        
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    
                    # Skip multipart containers
                    if content_type == "multipart/alternative" or content_type == "multipart/mixed":
                        continue
                    
                    # Check for attachments
                    if "attachment" in content_disposition or "filename" in content_disposition:
                        has_attachments = True
                        filename = part.get_filename()
                        if filename:
                            attachments.append(filename)
                        continue
                    
                    # Get text body
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        try:
                            payload = part.get_payload(decode=True)
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='ignore')
                        except:
                            pass
            else:
                # Simple email without multipart
                try:
                    payload = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='ignore')
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error extracting email content: {e}")
        
        # Clean body text
        body = re.sub(r'\s+', ' ', body).strip()
        return body, has_attachments, attachments
    
    def format_telegram_message(self, email_data: Dict) -> str:
        """Format email data for Telegram message"""
        subject = self.escape_markdown(email_data['subject'])
        from_name = self.escape_markdown(email_data['from_name'])
        from_email = email_data['from_email']
        date = email_data['date']
        body_preview = self.escape_markdown(email_data['body'][:500])  # Limit preview length
        
        # Format attachments info
        attachments_info = ""
        if email_data['has_attachments']:
            if email_data['attachments']:
                attachment_names = [self.escape_markdown(name) for name in email_data['attachments'][:3]]
                attachments_info = f"📎 *Attachments:* {', '.join(attachment_names)}"
                if len(email_data['attachments']) > 3:
                    attachments_info += f" (+{len(email_data['attachments']) - 3} more)"
            else:
                attachments_info = "📎 *Has attachments*"
        
        message = f"""
📬 *New Email Received*

*From:* {from_name}
`{from_email}`
*Subject:* {subject}
*Date:* {date}

{attachments_info}

*Preview:*
{body_preview}...
"""
        
        return message.strip()
    
    def escape_markdown(self, text: str) -> str:
        """Escape Markdown special characters for Telegram"""
        if not text:
            return ""
        escape_chars = r'\_*[]()~`>#+-=|{}.!'
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    def send_telegram_notification(self, message: str):
        """Send notification to Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Telegram notification sent successfully")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False
    
    def check_emails(self):
        """Main email checking function"""
        logger.info("Starting email check...")
        
        mail = self.connect_imap()
        if not mail:
            logger.error("Failed to connect to IMAP server")
            return
        
        try:
            # Get latest emails
            latest_uids = self.get_latest_uids(mail, count=20)
            
            if not latest_uids:
                logger.info("No emails found in inbox")
                return
            
            # Filter for new emails (UIDs greater than last checked)
            last_uid = self.state.get('last_uid', 0)
            new_uids = [uid for uid in latest_uids if uid > last_uid]
            
            if not new_uids:
                logger.info(f"No new emails (last UID: {last_uid})")
                return
            
            logger.info(f"Found {len(new_uids)} new email(s)")
            
            # Process new emails (from oldest to newest)
            for uid in sorted(new_uids):
                msg = self.fetch_email(mail, uid)
                if msg:
                    email_data = self.parse_email(msg)
                    
                    # Skip if email is empty or spam-like
                    if self.should_notify(email_data):
                        telegram_message = self.format_telegram_message(email_data)
                        if self.send_telegram_notification(telegram_message):
                            # Mark as processed
                            self.state.setdefault('processed_emails', []).append(uid)
                            logger.info(f"Processed email UID {uid}: {email_data['subject'][:50]}...")
                    
                    # Update last UID
                    if uid > last_uid:
                        last_uid = uid
            
            # Update state
            self.state['last_uid'] = last_uid
            self.save_state()
            
            logger.info(f"Email check completed. Last UID: {last_uid}")
            
        except Exception as e:
            logger.error(f"Error during email check: {e}")
        finally:
            try:
                mail.close()
                mail.logout()
            except:
                pass
    
    def should_notify(self, email_data: Dict) -> bool:
        """Filter to decide whether to notify about an email"""
        subject = email_data['subject'].lower()
        sender = email_data['from_email'].lower()
        
        # Skip common spam patterns
        spam_keywords = [
            'unsubscribe', 'newsletter', 'promotion', 'special offer',
            'dear customer', 'valued customer', 'notification'
        ]
        
        # Skip if subject contains spam keywords
        if any(keyword in subject for keyword in spam_keywords):
            logger.info(f"Skipping email (spam keyword): {subject[:50]}...")
            return False
        
        # Optional: Add specific sender whitelist/blacklist
        # Example: Whitelist important senders
        # important_senders = ['important@company.com']
        # if sender not in important_senders:
        #     return False
        
        return True
    
    def run(self):
        """Main bot loop"""
        logger.info("=" * 50)
        logger.info("Outlook Telegram Notifier Bot Started")
        logger.info(f"Email: {self.email_address}")
        logger.info(f"Check interval: {self.check_interval} seconds")
        logger.info("=" * 50)
        
        # Initial check
        self.check_emails()
        
        # Continuous checking loop
        while True:
            try:
                logger.info(f"Sleeping for {self.check_interval} seconds...")
                time.sleep(self.check_interval)
                
                # Perform check
                self.check_emails()
                
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(60)  # Wait before retrying

def main():
    """Entry point for the application"""
    notifier = OutlookTelegramNotifier()
    notifier.run()

if __name__ == "__main__":
    main()
