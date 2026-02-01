from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import os
from dotenv import load_dotenv
from datetime import datetime
import secrets

from database import Session, User
from outlook_auth import OutlookAuth
from email_service import EmailService

load_dotenv()

class OutlookEmailBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
        
        self.auth = OutlookAuth()
        self.email_service = EmailService()
        
        # Track active connections
        self.active_connections = {}
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_text = """
        📧 *Outlook Email Bot*
        
        I'll help you manage your Outlook emails right here in Telegram!
        
        *Available Commands:*
        /connect - Connect your Outlook account (new link each time!)
        /inbox - View your latest emails
        /stored - View stored emails
        /help - Show help information
        /disconnect - Disconnect your account
        /status - Check connection status
        
        🔐 *Each /connect generates a unique, secure link*
        """
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def connect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /connect command - generates UNIQUE link each time"""
        telegram_id = str(update.effective_user.id)
        username = update.effective_user.username or update.effective_user.first_name
        
        # Check if already connected
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if user and user.is_connected:
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Generate New Link", callback_data="new_auth"),
                    InlineKeyboardButton("📧 View Inbox", callback_data="view_inbox")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"👋 Hello {username}!\n\n"
                f"✅ *Already Connected*\n"
                f"Account: `{user.outlook_email}`\n"
                f"Connected: {user.updated_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Click below to generate a *new connection link* or view inbox:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Generate UNIQUE auth URL
        auth_url = self.auth.get_auth_url(telegram_id)
        
        # Add random parameter to ensure uniqueness in browser cache
        random_param = secrets.token_urlsafe(8)
        timestamp = int(datetime.utcnow().timestamp())
        unique_auth_url = f"{auth_url}&_t={timestamp}&_r={random_param}"
        
        # Create inline keyboard
        keyboard = [[
            InlineKeyboardButton(
                "🔗 Click Here to Connect Outlook", 
                url=unique_auth_url
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        connection_message = f"""
        👋 Hello {username}!
        
        📧 *Outlook Connection Request*
        
        🔐 *Unique Connection Link*
        • User ID: `{telegram_id[:8]}...`
        • Request Time: {datetime.now().strftime('%H:%M:%S')}
        • Link ID: {random_param[:8]}
        
        📝 *Steps:*
        1. Click the button below *(new unique link)*
        2. Sign in with your Microsoft account
        3. Grant permission to read emails
        4. You'll be redirected back
        
        ⚠️ *Important:*
        • This link expires in 10 minutes
        • Each /connect creates a new link
        • Old links won't work
        
        🔒 *Security:*
        • Your password is never stored
        • We only request read access
        """
        
        await update.message.reply_text(
            connection_message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Store connection attempt
        self.active_connections[telegram_id] = {
            'username': username,
            'requested_at': datetime.utcnow(),
            'link_id': random_param[:8]
        }
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        telegram_id = str(query.from_user.id)
        
        if query.data == "new_auth":
            # Generate new unique auth URL
            auth_url = self.auth.get_auth_url(telegram_id)
            random_param = secrets.token_urlsafe(8)
            unique_auth_url = f"{auth_url}&_r={random_param}"
            
            keyboard = [[
                InlineKeyboardButton(
                    "🔗 New Connection Link", 
                    url=unique_auth_url
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                f"🔐 *New Unique Connection Link*\n\n"
                f"Link ID: `{random_param[:8]}`\n"
                f"Generated: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"Click below to connect:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
        elif query.data == "view_inbox":
            await self.inbox(query, context)
    
    async def handle_auth_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle OAuth callback from web server"""
        # This would be triggered by your web server
        # You need to implement webhook or polling endpoint
        
        message_text = update.message.text if update.message else ""
        
        if "code=" in message_text and "state=" in message_text:
            # Parse code and state from message
            # This is simplified - you need proper parsing
            await update.message.reply_text(
                "🔄 Processing authentication...",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def inbox(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /inbox command"""
        telegram_id = str(update.effective_user.id)
        username = update.effective_user.username or update.effective_user.first_name
        
        # Check connection
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user or not user.is_connected:
            await update.message.reply_text(
                f"👋 Hello {username}!\n\n"
                "❌ *Not Connected*\n"
                "Please use /connect to generate a new link and connect your Outlook account first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        await update.message.reply_text(
            f"👋 Hello {username}!\n\n"
            f"📬 *Fetching emails for {user.outlook_email}...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Get emails
        emails = self.email_service.get_emails(telegram_id, limit=5)
        
        if not emails:
            await update.message.reply_text(
                f"📭 *No new emails found* in your inbox.\n"
                f"Last checked: {datetime.now().strftime('%H:%M:%S')}",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Display emails
        response = f"📧 *Latest Emails ({len(emails)})*\n"
        response += f"Account: `{user.outlook_email}`\n"
        response += f"Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
        
        for i, email in enumerate(emails, 1):
            attachments = "📎 " if email['has_attachments'] else ""
            read_status = "✅ " if email['is_read'] else "🆕 "
            
            response += f"{read_status}*{i}. {email['subject']}*\n"
            response += f"   👤 *From:* {email['sender']}\n"
            response += f"   📝 {email['preview']}\n"
            response += f"   🕒 {email['date'][:10]} {email['date'][11:16]}\n"
            response += f"   {attachments}\n\n"
        
        response += "💾 *Emails are automatically stored locally*\n"
        response += "Use /stored to view all stored emails"
        
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
            read_status = "✅ " if email.is_read else "🆕 "
            
            response += f"{read_status}*{i}. {email.subject[:50]}...*\n"
            response += f"   👤 *From:* {email.sender}\n"
            response += f"   🕒 {email.received_at.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"   {attachments}\n\n"
        
        response += "🔍 Use /search <keyword> to find specific emails"
        
        await update.message.reply_text(
            response,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - check connection status"""
        telegram_id = str(update.effective_user.id)
        username = update.effective_user.username or update.effective_user.first_name
        
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if user and user.is_connected:
            # Check token expiry
            token_status = "🟢 Valid"
            if user.expires_at and datetime.utcnow() > user.expires_at:
                token_status = "🔴 Expired - use /connect to renew"
            elif user.expires_at:
                expires_in = (user.expires_at - datetime.utcnow()).total_seconds() / 3600
                if expires_in < 1:
                    token_status = f"🟡 Expires in {int(expires_in*60)} minutes"
                else:
                    token_status = f"🟢 Expires in {int(expires_in)} hours"
            
            status_text = f"""
            👋 Hello {username}!
            
            🔵 *Connection Status: CONNECTED*
            
            📧 *Account Details:*
            • Email: `{user.outlook_email}`
            • Connected: {user.created_at.strftime('%Y-%m-%d')}
            • Last Updated: {user.updated_at.strftime('%Y-%m-%d %H:%M')}
            
            🔐 *Token Status:*
            • {token_status}
            
            ⚡ *Quick Actions:*
            • /inbox - View latest emails
            • /stored - View stored emails
            • /connect - Generate new link
            • /disconnect - Remove connection
            """
        else:
            status_text = f"""
            👋 Hello {username}!
            
            🔴 *Connection Status: NOT CONNECTED*
            
            You haven't connected your Outlook account yet.
            
            🔗 *To get started:*
            1. Use /connect to generate a unique link
            2. Click the link and sign in
            3. Grant permission to read emails
            4. Start managing emails in Telegram!
            
            🔒 *We never store your password*
            """
        
        await update.message.reply_text(
            status_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def disconnect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /disconnect command"""
        telegram_id = str(update.effective_user.id)
        username = update.effective_user.username or update.effective_user.first_name
        
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if user:
            email = user.outlook_email
            session.delete(user)
            session.commit()
            
            # Remove from active connections
            if telegram_id in self.active_connections:
                del self.active_connections[telegram_id]
            
            await update.message.reply_text(
                f"👋 Goodbye {username}!\n\n"
                f"✅ *Disconnected Successfully!*\n"
                f"Account `{email}` has been unlinked.\n\n"
                f"All stored data has been removed.\n\n"
                f"Use /connect anytime to reconnect.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"👋 Hello {username}!\n\n"
                "ℹ️ *No account connected.*\n"
                "Use /connect to link your Outlook account.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = f"""
        👋 Hello! I'm your Outlook Email Bot.
        
        📖 *Commands Guide:*
        
        🔗 *Connection:*
        • `/connect` - Generate NEW unique link to connect Outlook
        • `/status` - Check your connection status
        • `/disconnect` - Unlink your account
        
        📧 *Email Management:*
        • `/inbox` - View latest emails (auto-stores them)
        • `/stored` - View locally stored emails
        • `/search <keyword>` - Search emails
        
        ℹ️ *Information:*
        • `/help` - This help message
        • `/start` - Welcome message
        
        🔐 *Security Features:*
        • Each /connect creates a UNIQUE link
        • Links expire in 10 minutes
        • Old links automatically invalidated
        • Your password is never stored
        • Read-only email access
        
        💡 *Tip:* Use /connect anytime to generate a fresh link!
        """
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command"""
        if not context.args:
            await update.message.reply_text(
                "🔍 *Search Usage:*\n"
                "`/search keyword` - Search emails by subject or sender\n"
                "Example: `/search invoice`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        telegram_id = str(update.effective_user.id)
        query = ' '.join(context.args)
        
        emails = self.email_service.search_emails(telegram_id, query)
        
        if not emails:
            await update.message.reply_text(
                f"🔍 *No results found for:* `{query}`\n"
                "Try different keywords or check /inbox first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        response = f"🔍 *Search Results for '{query}'* ({len(emails)} found)\n\n"
        
        for i, email in enumerate(emails, 1):
            attachments = "📎 " if email.has_attachments else ""
            response += f"*{i}. {email.subject[:60]}...*\n"
            response += f"   👤 *From:* {email.sender}\n"
            response += f"   🕒 {email.received_at.strftime('%Y-%m-%d')}\n"
            response += f"   {attachments}\n\n"
        
        await update.message.reply_text(
            response,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    
    def run(self):
        """Start the bot"""
        app = Application.builder().token(self.token).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("connect", self.connect))
        app.add_handler(CommandHandler("inbox", self.inbox))
        app.add_handler(CommandHandler("stored", self.stored))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("disconnect", self.disconnect))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("search", self.search))
        
        # Callback handlers
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Message handler for auth callback
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_auth_callback))
        
        print("🤖 Outlook Email Bot is running...")
        print("🔗 Each /connect command generates a UNIQUE link!")
        print("📧 Use /connect to get started")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot = OutlookEmailBot()
    bot.run()
