import aiohttp
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

async def fetch_user_emails(access_token: str, limit: int = 10) -> List[Dict]:
    """
    Fetch emails from Microsoft Graph API
    """
    graph_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    
    params = {
        "$top": limit,
        "$orderby": "receivedDateTime DESC",
        "$select": "subject,from,receivedDateTime,hasAttachments,isRead,bodyPreview",
        "$filter": "isDraft eq false"
    }
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Prefer": 'outlook.body-content-type="text"'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(graph_url, headers=headers, params=params) as response:
                
                if response.status == 200:
                    data = await response.json()
                    emails = data.get('value', [])
                    
                    logger.info(f"Successfully fetched {len(emails)} emails")
                    return emails
                    
                elif response.status == 401:
                    logger.error("Unauthorized - Token expired or invalid")
                    return []
                    
                elif response.status == 403:
                    logger.error("Forbidden - Insufficient permissions")
                    return []
                    
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to fetch emails: {response.status} - {error_text}")
                    return []
                    
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching emails: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching emails: {e}")
        return []

def format_email_for_display(email: Dict) -> str:
    """
    Format email for Telegram display
    """
    try:
        sender = email.get('from', {}).get('emailAddress', {})
        sender_name = sender.get('name', 'Unknown Sender')
        sender_email = sender.get('address', '')
        
        subject = email.get('subject', 'No Subject')
        if not subject or subject.strip() == '':
            subject = '(No Subject)'
        
        received = email.get('receivedDateTime', '')
        if received:
            # Format: "Jan 1, 2023 14:30"
            from datetime import datetime
            dt = datetime.fromisoformat(received.replace('Z', '+00:00'))
            received = dt.strftime("%b %d, %Y %H:%M")
        
        has_attachments = email.get('hasAttachments', False)
        is_read = email.get('isRead', True)
        
        # Preview (first 100 chars)
        body_preview = email.get('bodyPreview', '')
        if body_preview:
            preview = body_preview[:100] + "..." if len(body_preview) > 100 else body_preview
        else:
            preview = "No preview available"
        
        # Format the message
        formatted = f"**{subject}**\n"
        formatted += f"👤 *From:* {sender_name}\n"
        if sender_email:
            formatted += f"📧 {sender_email}\n"
        formatted += f"🕐 *Received:* {received}\n"
        
        if has_attachments:
            formatted += "📎 *Has attachments*\n"
        
        if not is_read:
            formatted += "🔵 *Unread*\n"
        
        formatted += f"\n📋 *Preview:* {preview}\n"
        formatted += "─" * 40
        
        return formatted
        
    except Exception as e:
        logger.error(f"Error formatting email: {e}")
        return "Error formatting email content"
