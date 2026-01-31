#!/usr/bin/env python3
"""
Interactive Outlook Email Watcher Telegram Bot
Users can register their credentials through the bot
"""

import os
import logging
import sys
import asyncio
from datetime import datetime
from typing import Dict, Optional
import re

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

from email_monitor import EmailMonitor
from users_db import UserDatabase

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
START, EMAIL, PASSWORD, CONFIRM, MENU = range(5)

class OutlookEmailWatcherBot:
    def __init__(self):
        """Initialize the bot"""
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.telegram_token:
            logger.error("TELEGRAM_BOT_TOKEN environment variable not set")
            sys.exit(1)
        
        self.user_db = UserDatabase()
        self.email_monitors: Dict[int, EmailMonitor] = {}
        
        # Create application
        self.application = Application.builder().token(self.telegram_token).build()
        
        # Set up conversation handler
        self.setup_handlers()
        
    def setup_handlers(self):
        """Set up all Telegram handlers"""
        
        # Conversation handler for registration
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_email)],
                PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_password)],
                CONFIRM: [CallbackQueryHandler(self.confirm_credentials)],
                MENU: [
                    CallbackQueryHandler(self.menu_handler),
                    CommandHandler('stop', self.stop_monitoring),
                    CommandHandler('status', self.check_status),
                    CommandHandler('help', self.help_command)
                ]
            },
            fallbacks=[CommandHandler('cancel', self.cancel_command)],
            allow_reentry=True
        )
        
        # Add handlers
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler('help', self.help_command))
        self.application.add_handler(CommandHandler('status', self.check_status))
        self.application.add_handler(CommandHandler('stop', self.stop_monitoring))
        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start command - begin the conversation"""
        user_id = update.effective_user.id
        
        # Check if user is already registered
        if self.user_db.user_exists(user_id):
            await update.message.reply_text(
                "👋 Welcome back!\n\n"
                "You're already registered. Here are your options:",
                reply_markup=self.get_main_menu_keyboard()
            )
            return MENU
        
        await update.message.reply_text(
            "👋 Welcome to Outlook Email Watcher Bot!\n\n"
            "I'll monitor your Outlook inbox and notify you of new emails.\n\n"
            "📧 Please enter your Outlook email address:"
        )
        return EMAIL
    
    async def get_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get email address from user"""
        email = update.message.text.strip()
        
        # Validate email format
        if not self.is_valid_email(email):
            await update.message.reply_text(
                "❌ Invalid email format. Please enter a valid Outlook email address:"
            )
            return EMAIL
        
        # Save email to context
        context.user_data['email'] = email
        
        await update.message.reply_text(
            f"📧 Email received: {email}\n\n"
            "🔐 Now, please enter your password:\n\n"
            "⚠️ Note: If you have 2FA enabled, you'll need to use an "
            "App Password from Microsoft."
        )
        return PASSWORD
    
    async def get_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get password from user"""
        password = update.message.text.strip()
        
        # Save password to context
        context.user_data['password'] = password
        
        # Show confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, start monitoring", callback_data="confirm"),
                InlineKeyboardButton("❌ No, change email", callback_data="change_email")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📋 Please confirm your credentials:\n\n"
            f"📧 Email: {context.user_data['email']}\n"
            f"🔐 Password: {'*' * len(password)}\n\n"
            f"Click 'Yes' to start monitoring your inbox:",
            reply_markup=reply_markup
        )
        return CONFIRM
    
    async def confirm_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle confirmation of credentials"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if query.data == "confirm":
            email = context.user_data['email']
            password = context.user_data['password']
            
            try:
                # Test connection with provided credentials
                await query.edit_message_text("🔐 Testing your credentials...")
                
                # Test IMAP connection
                monitor = EmailMonitor(user_id, email, password)
                test_result = await asyncio.to_thread(monitor.test_connection)
                
                if test_result:
                    # Save user credentials
                    self.user_db.save_user(user_id, email, password)
                    
                    # Start monitoring
                    await self.start_user_monitoring(user_id, email, password, update, context)
                    
                    await query.edit_message_text(
                        "✅ Registration successful!\n\n"
                        f"📧 Now monitoring: {email}\n"
                        "⏱️ Checking for new emails every 30 minutes\n\n"
                        "You'll receive notifications for new emails here.",
                        reply_markup=self.get_main_menu_keyboard()
                    )
                    return MENU
                else:
                    await query.edit_message_text(
                        "❌ Failed to connect to Outlook.\n\n"
                        "Possible issues:\n"
                        "1. Incorrect email or password\n"
                        "2. IMAP not enabled in Outlook settings\n"
                        "3. 2FA enabled (use App Password)\n\n"
                        "Please try again with /start"
                    )
                    return ConversationHandler.END
                    
            except Exception as e:
                logger.error(f"Error during registration: {e}")
                await query.edit_message_text(
                    f"❌ Error: {str(e)}\n\n"
                    "Please try again with /start"
                )
                return ConversationHandler.END
        
        elif query.data == "change_email":
            await query.edit_message_text("📧 Please enter your Outlook email address:")
            return EMAIL
    
    async def start_user_monitoring(self, user_id: int, email: str, password: str, 
                                   update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start email monitoring for a user"""
        try:
            # Create and start monitor
            monitor = EmailMonitor(user_id, email, password)
            self.email_monitors[user_id] = monitor
            
            # Start monitoring in background
            asyncio.create_task(self.monitor_emails_loop(user_id, monitor, context))
            
            logger.info(f"Started monitoring for user {user_id} ({email})")
            
        except Exception as e:
            logger.error(f"Failed to start monitoring for user {user_id}: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Failed to start monitoring: {str(e)}"
            )
    
    async def monitor_emails_loop(self, user_id: int, monitor: EmailMonitor, 
                                 context: ContextTypes.DEFAULT_TYPE):
        """Continuous email monitoring loop for a user"""
        check_interval = 1800  # 30 minutes
        
        while user_id in self.email_monitors:
            try:
                # Check for new emails
                new_emails = await asyncio.to_thread(monitor.check_new_emails)
                
                # Send notifications for new emails
                for email_data in new_emails:
                    await self.send_email_notification(user_id, email_data, context)
                
                # Wait for next check
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop for user {user_id}: {e}")
                await asyncio.sleep(60)  # Wait before retry
    
    async def send_email_notification(self, user_id: int, email_data: Dict, 
                                     context: ContextTypes.DEFAULT_TYPE):
        """Send email notification to user"""
        try:
            message = self.format_email_notification(email_data)
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to send notification to user {user_id}: {e}")
    
    def format_email_notification(self, email_data: Dict) -> str:
        """Format email data for Telegram notification"""
        subject = self.escape_html(email_data.get('subject', 'No Subject'))
        sender_name = self.escape_html(email_data.get('from_name', 'Unknown'))
        sender_email = email_data.get('from_email', '')
        preview = self.escape_html(email_data.get('preview', '')[:200])
        
        # Format attachments info
        attachments = email_data.get('attachments', [])
        attachments_info = ""
        if attachments:
            attachments_info = f"\n📎 <b>Attachments:</b> {len(attachments)} file(s)"
        
        message = f"""
📬 <b>New Email Received</b>

<b>From:</b> {sender_name}
<code>{sender_email}</code>

<b>Subject:</b> {subject}

<b>Preview:</b>
{preview}...
{attachments_info}
"""
        return message.strip()
    
    def escape_html(self, text: str) -> str:
        """Escape HTML special characters"""
        if not text:
            return ""
        html_escape_table = {
            "&": "&amp;",
            '"': "&quot;",
            "'": "&apos;",
            ">": "&gt;",
            "<": "&lt;"
        }
        return "".join(html_escape_table.get(c, c) for c in text)
    
    async def menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle main menu actions"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if query.data == "status":
            if user_id in self.email_monitors:
                status = await asyncio.to_thread(self.email_monitors[user_id].get_status)
                await query.edit_message_text(
                    f"📊 <b>Monitoring Status</b>\n\n"
                    f"{status}\n\n"
                    f"Last check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    parse_mode='HTML',
                    reply_markup=self.get_main_menu_keyboard()
                )
            else:
                await query.edit_message_text(
                    "❌ Monitoring is not active.\n"
                    "Use /start to start monitoring.",
                    reply_markup=self.get_main_menu_keyboard()
                )
        
        elif query.data == "help":
            await query.edit_message_text(
                self.get_help_text(),
                parse_mode='HTML',
                reply_markup=self.get_main_menu_keyboard()
            )
        
        return MENU
    
    async def stop_monitoring(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Stop email monitoring"""
        user_id = update.effective_user.id
        
        if user_id in self.email_monitors:
            # Stop monitoring
            self.email_monitors.pop(user_id, None)
            
            # Clear user data (optional)
            # self.user_db.delete_user(user_id)
            
            await update.message.reply_text(
                "🛑 Monitoring stopped.\n\n"
                "Your credentials have been removed.\n"
                "Use /start to set up monitoring again."
            )
        else:
            await update.message.reply_text(
                "ℹ️ No active monitoring session found.\n"
                "Use /start to begin monitoring."
            )
    
    async def check_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check monitoring status"""
        user_id = update.effective_user.id
        
        if user_id in self.email_monitors:
            status = await asyncio.to_thread(self.email_monitors[user_id].get_status)
            await update.message.reply_text(
                f"📊 <b>Monitoring Status</b>\n\n{status}",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "❌ No active monitoring session.\n"
                "Use /start to begin monitoring."
            )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show help message"""
        await update.message.reply_text(
            self.get_help_text(),
            parse_mode='HTML'
        )
    
    def get_help_text(self) -> str:
        """Get help text"""
        return """
<b>📧 Outlook Email Watcher Bot</b>

<b>Commands:</b>
/start - Start or reconfigure monitoring
/stop - Stop monitoring and remove credentials
/status - Check monitoring status
/help - Show this help message

<b>Features:</b>
• Monitors your Outlook inbox
• Sends notifications for new emails
• Checks every 30 minutes
• Secure credential storage
• Attachment detection

<b>Setup Notes:</b>
1. IMAP must be enabled in Outlook settings
2. If you have 2FA, use an App Password
3. Notifications will be sent here

<b>Privacy:</b>
• Credentials are encrypted
• Only email metadata is accessed
• No emails are stored permanently
"""
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation"""
        await update.message.reply_text(
            "Operation cancelled.\n"
            "Use /start to begin setup again."
        )
        return ConversationHandler.END
    
    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle unknown commands"""
        await update.message.reply_text(
            "Sorry, I didn't understand that command.\n"
            "Use /help to see available commands."
        )
    
    def get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Get main menu keyboard"""
        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="status")],
            [InlineKeyboardButton("❓ Help", callback_data="help")],
            [InlineKeyboardButton("🛑 Stop Monitoring", callback_data="stop")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def is_valid_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")
        
        if update and update.effective_user:
            try:
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text="❌ An error occurred. Please try again."
                )
            except:
                pass
    
    def run(self):
        """Run the bot"""
        logger.info("Starting Outlook Email Watcher Bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

async def main():
    """Main function"""
    bot = OutlookEmailWatcherBot()
    await bot.application.initialize()
    await bot.application.start()
    await bot.application.updater.start_polling()
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
