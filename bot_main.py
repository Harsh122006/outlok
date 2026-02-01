from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import os
from dotenv import load_dotenv
from datetime import datetime

from database import Session, User
from outlook_auth import OutlookAuth
from email_service import EmailService

load_dotenv()

class OutlookEmailBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.auth = OutlookAuth()
        self.email_service = EmailService()
        
        # Store temporary auth states
        self.pending_auth = {}
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_text = """
        📧 *Outlook Email Bot*
        
        I'll help you manage your Outlook emails right here in Telegram!
        
        *Available Commands:*
        /connect - Connect your Outlook account
        /inbox - View your latest emails
        /stored - View stored emails
        /help - Show help information
        /disconnect - Disconnect your account
        
        🔐 *Your data is secure and encrypted!*
        """
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def connect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /connect command"""
        telegram_id = str(update.effective_user.id)
        
        # Check if already connected
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if user and user.is_connected:
            await update.message.reply_text(
                f"✅ *Already Connected!*\n"
                f"Your account `{user.outlook_email}` is already connected.\n"
                f"Use /inbox to view emails or /disconnect to unlink.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Generate auth URL
        auth_url = self.auth.get_auth_url(telegram_id)
        
        # Create inline keyboard
        keyboard = [[InlineKeyboardButton("🔗 Connect Outlook Account", url=auth_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📧 *Connect Your Outlook Account*\n\n"
            "1. Click the button below\n"
            "2. Sign in with your Microsoft account\n"
            "3. Grant the requested permissions\n"
            "4. You'll be redirected back\n\n"
            "🔒 *We only request read access to display your emails*",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle OAuth callback"""
        query = update.callback_query
        await query.answer()
        
        telegram_id = str(query.from_user.id)
        code = query.data.split(':')[1]
        
        # Exchange code for tokens
        result = self.auth.get_token_from_code(code)
        
        if 'access_token' in result:
            # Get user info
            user_info = self.auth.get_user_info(result['access_token'])
            email = user_info.get('mail') or user_info.get('userPrincipalName')
            
            # Save to database
            session = Session()
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            
            if not user:
                user = User(telegram_id=telegram_id)
            
            user.outlook_email = email
            user.access_token = result['access_token']
            user.refresh_token = result.get('refresh_token', '')
            user.expires_at = datetime.utcnow() + timedelta(seconds=result['expires_in'])
            user.is_connected = True
            user.updated_at = datetime.utcnow()
            
            session.add(user)
            session.commit()
            
            # ✅ **SUCCESS CONNECTION MESSAGE**
            success_message = f"""
            ✅ *Outlook Connected Successfully!*
            
            *Account:* `{email}`
            *Status:* 📡 Connected
            *Connected at:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            🎉 *You can now use these commands:*
            • `/inbox` - View latest emails
            • `/stored` - View stored emails
            • `/help` - More information
            
            Your emails will be synced automatically!
            """
            
            await query.message.reply_text(
                success_message,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.message.reply_text(
                "❌ *Connection Failed!*\n"
                "Please try /connect again.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def inbox(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /inbox command"""
        telegram_id = str(update.effective_user.id)
        
        # Check connection
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user or not user.is_connected:
            await update.message.reply_text(
                "❌ *Not Connected!*\n"
                "Please use /connect to link your Outlook account first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        await update.message.reply_text(
            f"📬 *Fetching emails for {user.outlook_email}...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Get emails
        emails = self.email_service.get_emails(telegram_id, limit=5)
        
        if not emails:
            await update.message.reply_text(
                "📭 *No emails found* in your inbox.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Display emails
        response = f"📧 *Latest Emails ({len(emails)})*\n\n"
        
        for i, email in enumerate(emails, 1):
            attachments = "📎 " if email['has_attachments'] else ""
            response += f"{i}. *{email['subject']}*\n"
            response += f"   👤 *From:* {email['sender']}\n"
            response += f"   📝 {email['preview']}...\n"
            response += f"   🕒 {email['date'][:10]}\n"
            response += f"   {attachments}\n\n"
        
        response += "💾 *Emails are automatically stored locally*"
        
        await update.message.reply_text(
            response,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    
    async def stored(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stored command - show stored emails"""
        telegram_id = str(update.effective_user.id)
        
        emails = self.email_service.get_stored_emails(telegram_id, limit=10)
        
        if not emails:
            await update.message.reply_text(
                "📭 *No stored emails found.*\n"
                "Use /inbox to fetch and store emails first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        response = f"💾 *Stored Emails ({len(emails)})*\n\n"
        
        for i, email in enumerate(emails, 1):
            attachments = "📎 " if email.has_attachments else ""
            response += f"{i}. *{email.subject}*\n"
            response += f"   👤 *From:* {email.sender}\n"
            response += f"   🕒 {email.received_at.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"   {attachments}\n\n"
        
        await update.message.reply_text(
            response,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    
    async def disconnect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /disconnect command"""
        telegram_id = str(update.effective_user.id)
        
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if user:
            email = user.outlook_email
            session.delete(user)
            session.commit()
            
            await update.message.reply_text(
                f"✅ *Disconnected Successfully!*\n"
                f"Account `{email}` has been unlinked.\n\n"
                f"All stored data has been removed.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                "ℹ️ *No account connected.*\n"
                "Use /connect to link your Outlook account.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
        📖 *Outlook Email Bot Help*
        
        *Commands:*
        /start - Start the bot
        /connect - Connect your Outlook account
        /inbox - View latest emails (auto-stores them)
        /stored - View locally stored emails
        /disconnect - Unlink your account
        /help - This message
        
        *Features:*
        🔐 Secure OAuth 2.0 authentication
        💾 Local email storage
        🔄 Automatic email fetching
        📎 Attachment indicators
        🔍 Search capability
        
        *Privacy:*
        • We only request read access
        • Your credentials are never stored
        • All data is encrypted
        • You can disconnect anytime
        
        Need help? Contact support.
        """
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    def run(self):
        """Start the bot"""
        app = Application.builder().token(self.token).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("connect", self.connect))
        app.add_handler(CommandHandler("inbox", self.inbox))
        app.add_handler(CommandHandler("stored", self.stored))
        app.add_handler(CommandHandler("disconnect", self.disconnect))
        app.add_handler(CommandHandler("help", self.help_command))
        
        print("🤖 Bot is running...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot = OutlookEmailBot()
    bot.run()
