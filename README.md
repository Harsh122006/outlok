# Outlook Email to Telegram Notifier

A Python bot that monitors your Outlook inbox and sends notifications to Telegram when new emails arrive. Deployed on Railway with 30-minute checks.

## Features

- ✅ Monitors Outlook/Office365 emails via IMAP
- ✅ Sends notifications to Telegram with email preview
- ✅ Attachment detection
- ✅ Markdown formatting
- ✅ State persistence between runs
- ✅ Spam filtering
- ✅ Deployable on Railway

## Setup

### 1. Outlook Configuration

#### Enable IMAP Access:
1. Go to Outlook.com → Settings → View all Outlook settings
2. Navigate to Mail → Sync email
3. Under "POP and IMAP", toggle IMAP to **ON**
4. Save changes

#### Create App Password (if using 2FA):
1. Go to [Microsoft Security Settings](https://account.microsoft.com/security)
2. Under "Advanced security options", select "Create a new app password"
3. Generate password for "Other app" (name it "Telegram Bot")
4. Save this password

### 2. Telegram Bot Setup

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Create a new bot with `/newbot`
3. Save the **Bot Token** provided
4. Start a chat with your new bot
5. Get your **Chat ID** by messaging [@userinfobot](https://t.me/userinfobot)

### 3. Local Testing

```bash
# Clone repository
git clone <your-repo-url>
cd outlook-telegram-notifier

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env

# Install dependencies
pip install -r requirements.txt

# Run locally
python bot.py
