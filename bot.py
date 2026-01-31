import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
import imaplib
import email
from email.header import decode_header
import re
import json
from datetime import datetime

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
EMAIL, PASSWORD, CONFIRM, MENU = range(4)

# Store user sessions
user_sessions = {}
user_monitors = {}

class EmailMonitor:
    def __init__(self, user_id, email, password):
        self.user_id = user_id
        self.email = email
        self.password = password
        self.last_uid = 0
        self.state_file = f'state_{user_id}.json'
        self.load_state()
        
    def load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.last_uid = state.get('last_uid', 0)
        except:
            pass
            
    def save_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump({'last_uid': self.last_uid}, f)
        except:
            pass
    
    def test_connection(self):
        """Test if credentials work"""
        try:
            mail = imaplib.IMAP4_SSL('outlook.office365.com', 993)
            mail.login(self.email, self.password)
            mail.select('INBOX')
            mail.logout()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def check_emails(self):
        """Check for new emails"""
        try:
            mail = imaplib.IMAP4_SSL('outlook.office365.com', 993)
            mail.login(self.email, self.password)
            mail.select('INBOX')
            
            # Get all UIDs
            status, data = mail.uid('search', None, 'ALL')
            if status != 'OK' or not data[0]:
                return []
            
            all_uids = [int(uid) for uid in data[0].split()]
            new_uids = [uid for uid in all_uids if uid > self.last_uid]
            
            new_emails = []
            if new_uids:
                for uid in sorted(new_uids):
                    email_data = self.fetch_email(mail, uid)
                    if email_data:
                        new_emails.append(email_data)
                
                # Update last UID
                self.last_uid = max(new_uids)
                self.save_state()
            
            mail.logout()
            return new_emails
            
        except Exception as e:
            logger.error(f"Error checking emails: {e}")
            return []
    
    def fetch_email(self, mail, uid):
        """Fetch a single email"""
        try:
            status, data = mail.uid('fetch', str(uid).encode(), '(RFC822)')
            if status != 'OK':
                return None
            
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Parse subject
            subject, encoding = decode_header(msg.get('Subject', ''))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else 'utf-8')
            
            # Parse sender
            from_header = msg.get('From', '')
            sender_name, sender_email = self.parse_sender(from_header)
            
            # Get preview
            body_preview = self.get_email_preview(msg)
            
            return {
                'subject': subject or 'No Subject',
                'from_name': sender_name,
                'from_email': sender_email,
                'preview': body_preview[:200] + '...' if len(body_preview) > 200 else body_preview,
                'date': msg.get('Date', '')
            }
            
        except Exception as e:
            logger.error(f"Error fetching email: {e}")
            return None
    
    def parse_sender(self, from_header):
        """Extract name and email from header"""
        try:
            match = re.match(r'"?([^"<]+)"?\s*<([^>]+)>', from_header)
            if match:
                return match.group(1).strip(), match.group(2).strip()
            
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', from_header)
            if email_match:
                return from_header, email_match.group(1)
                
        except:
            pass
        return 'Unknown', from_header
    
    def get_email_preview(self, msg):
        """Extract text preview from email"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        return payload.decode(charset, errors='ignore').strip()
                    except:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                return payload.decode(charset, errors='ignore').strip()
            except:
                pass
        return ""

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation"""
    user_id = update.effective_user.id
    
    if user_id in user_monitors:
        await update.message.reply_text(
            "✅ You're already monitoring your inbox!\n\n"
            "Use /stop to stop monitoring\n"
            "Use /status to check status"
        )
        return MENU
    
    await update.message.reply_text(
        "👋 Welcome to Outlook Email Watcher Bot!\n\n"
        "I'll monitor your Outlook inbox and notify you of new emails.\n\n"
        "📧 Please enter your Outlook email address:"
    )
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get email from user"""
    email_input = update.message.text.strip()
    
    # Basic email validation
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email_input):
        await update.message.reply_text(
            "❌ Invalid email format. Please enter a valid email address:"
        )
        return EMAIL
    
    # Store email in context
    context.user_data['email'] = email_input
    
    await update.message.reply_text(
        f"📧 Email saved: {email_input}\n\n"
        "🔐 Now, please enter your password:\n\n"
        "⚠️ **Important:** If you have 2FA enabled, you need to use an "
        "App Password from Microsoft.\n\n"
        "To create an app password:\n"
        "1. Go to https://account.microsoft.com/security\n"
        "2. Enable 2FA if not already\n"
        "3. Create a new app password\n"
        "4. Use that password here"
    )
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get password from user"""
    password = update.message.text.strip()
    
    if not password:
        await update.message.reply_text("Please enter a valid password:")
        return PASSWORD
    
    # Store password
    context.user_data['password'] = password
    
    # Create confirmation keyboard
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Start Monitoring", callback_data="confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📋 Confirm your details:\n\n"
        f"📧 Email: {context.user_data['email']}\n"
        f"🔐 Password: {'*' * len(password)}\n\n"
        f"Click below to start monitoring:",
        reply_markup=reply_markup
    )
    return CONFIRM

async def confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirmation"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == "confirm":
        email = context.user_data['email']
        password = context.user_data['password']
        
        await query.edit_message_text("🔐 Testing your credentials...")
        
        # Test connection
        monitor = EmailMonitor(user_id, email, password)
        if monitor.test_connection():
            # Save to active monitors
            user_monitors[user_id] = monitor
            
            # Start monitoring task
            asyncio.create_task(monitoring_task(user_id, monitor, context))
            
            await query.edit_message_text(
                f"✅ **Monitoring Started!**\n\n"
                f"📧 Now watching: {email}\n"
                f"⏰ Checking every 30 minutes\n"
                f"🔔 Notifications will appear here\n\n"
                "Use /stop to stop monitoring\n"
                "Use /status to check status"
            )
            return MENU
        else:
            await query.edit_message_text(
                "❌ **Connection Failed!**\n\n"
                "Possible issues:\n"
                "• Wrong email or password\n"
                "• IMAP not enabled in Outlook\n"
                "• 2FA enabled (use App Password)\n\n"
                "Try again with /start"
            )
            return ConversationHandler.END
    
    elif query.data == "cancel":
        await query.edit_message_text("❌ Setup cancelled.\nUse /start to try again.")
        return ConversationHandler.END

async def monitoring_task(user_id, monitor, context):
    """Background task to monitor emails"""
    while user_id in user_monitors:
        try:
            new_emails = monitor.check_emails()
            
            for email_data in new_emails:
                message = format_email_notification(email_data)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='HTML'
                )
            
            # Wait 30 minutes
            await asyncio.sleep(1800)
            
        except Exception as e:
            logger.error(f"Monitoring error for user {user_id}: {e}")
            await asyncio.sleep(60)

def format_email_notification(email_data):
    """Format email for Telegram notification"""
    subject = escape_html(email_data['subject'])
    sender = escape_html(email_data['from_name'])
    email_addr = email_data['from_email']
    preview = escape_html(email_data['preview'])
    
    return f"""
📬 <b>New Email Received</b>

<b>From:</b> {sender}
<code>{email_addr}</code>

<b>Subject:</b> {subject}

<b>Preview:</b>
{preview}
"""

def escape_html(text):
    """Escape HTML special characters"""
    return (text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop monitoring"""
    user_id = update.effective_user.id
    
    if user_id in user_monitors:
        del user_monitors[user_id]
        
        # Clean up state file
        state_file = f'state_{user_id}.json'
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except:
                pass
        
        await update.message.reply_text(
            "🛑 **Monitoring Stopped!**\n\n"
            "Your credentials have been removed.\n"
            "Use /start to set up monitoring again."
        )
    else:
        await update.message.reply_text(
            "ℹ️ No active monitoring found.\n"
            "Use /start to begin monitoring."
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check monitoring status"""
    user_id = update.effective_user.id
    
    if user_id in user_monitors:
        monitor = user_monitors[user_id]
        await update.message.reply_text(
            f"📊 **Monitoring Status**\n\n"
            f"📧 Email: {monitor.email}\n"
            f"✅ Status: Active\n"
            f"⏰ Next check: Soon\n"
            f"🔄 Interval: 30 minutes"
        )
    else:
        await update.message.reply_text(
            "❌ No active monitoring.\n"
            "Use /start to begin monitoring."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    help_text = """
🤖 <b>Outlook Email Watcher Bot</b>

<b>Commands:</b>
/start - Start monitoring your Outlook inbox
/stop - Stop monitoring
/status - Check monitoring status
/help - Show this message

<b>How to use:</b>
1. Use /start and enter your Outlook email
2. Enter your password (use App Password if 2FA enabled)
3. Bot will check for new emails every 30 minutes
4. Receive notifications here for new emails

<b>Note:</b>
• IMAP must be enabled in Outlook settings
• For 2FA accounts, use an App Password
• Your password is stored only while monitoring
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation"""
    await update.message.reply_text(
        "Setup cancelled.\n"
        "Use /start to try again."
    )
    return ConversationHandler.END

def main():
    """Start the bot"""
    # Get token from environment variable
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        logger.error("Please set it in Railway environment variables")
        return
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Set up conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            CONFIRM: [CallbackQueryHandler(confirm_handler)],
            MENU: [
                CommandHandler('stop', stop_command),
                CommandHandler('status', status_command),
                CommandHandler('help', help_command)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('stop', stop_command))
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
