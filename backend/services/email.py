"""Email service for sending invitations and notifications."""
from typing import Optional

from fastapi_mail import ConnectionConfig, MessageSchema, MessageType
from fastapi_mail.errors import ConnectionErrors
from sqlalchemy.ext.asyncio import AsyncSession

from config import config
from services.settings_service import settings_service


# Email configuration - will be initialized dynamically from database
email_config = None


class EmailService:
    """Email service for sending emails."""
    
    def __init__(self):
        self.config = email_config
    
    async def _get_email_config(self, db: AsyncSession):
        """Get email configuration from database."""
        email_settings = await settings_service.get_email_config(db)
        
        if not email_settings:
            return None
            
        return ConnectionConfig(
            MAIL_USERNAME=email_settings['smtp_username'],
            MAIL_PASSWORD=email_settings['smtp_password'],
            MAIL_FROM=email_settings['from_email'],
            MAIL_PORT=email_settings['smtp_port'],
            MAIL_SERVER=email_settings['smtp_server'],
            MAIL_STARTTLS=email_settings['use_tls'],
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True,
        )
    
    async def _get_frontend_url(self, db: AsyncSession) -> str:
        """Get frontend URL from config."""
        return config.FRONTEND_URL
    
    async def send_invite_email(
        self,
        to_email: str,
        invite_token: str,
        inviter_name: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> bool:
        """Send invitation email to user."""
        if not db:
            print(f"Email not configured. Would send invite to {to_email} with token {invite_token}")
            return True
            
        email_config = await self._get_email_config(db)
        if not email_config:
            print(f"Email not configured in database. Would send invite to {to_email} with token {invite_token}")
            return True
            
        try:
            # Create invite link pointing to user registration
            invite_link = "http://localhost:3000/register"
            
            # Prepare email content
            subject = "You're invited to join Confab Chat"
            
            # HTML email template
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Invitation to Join Confab Chat</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .content {{
                        background-color: #f9fafb;
                        padding: 30px;
                        border-radius: 8px;
                    }}
                    .button {{
                        display: inline-block;
                        background-color: #4f46e5;
                        color: white;
                        padding: 12px 24px;
                        text-decoration: none;
                        border-radius: 6px;
                        margin: 20px 0;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        color: #666;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="content">
                    <p>Hello,</p>
                    <p>You've been invited to join Confab Chat{f' by {inviter_name}' if inviter_name else ''}!</p>
                    <p>Confab Chat is an AI-powered chat platform that helps you get answers and assistance using advanced AI technology.</p>
                    <p>To get started, simply click the button below to accept your invitation and create your account:</p>
                    <div style="text-align: center;">
                        <a href="{invite_link}" class="button">Accept Invitation</a>
                    </div>
                    <p>If the button above doesn't work, you can also copy and paste this link into your browser:</p>
                    <p><a href="{invite_link}">{invite_link}</a></p>
                    <p>This invitation will expire in 7 days.</p>
                    <p>We look forward to having you join our community!</p>
                </div>
                <div class="footer">
                    <p>Best regards,<br>The Confab Chat Team</p>
                </div>
            </body>
            </html>
            """
            
            # Create message
            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=html_content,
                subtype=MessageType.html,
            )
            
            # Send email
            from fastapi_mail import FastMail
            fm = FastMail(email_config)
            await fm.send_message(message)
            
            return True
            
        except ConnectionErrors as e:
            print(f"Failed to send email: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error sending email: {e}")
            return False
    
    async def send_welcome_email(self, to_email: str, user_name: Optional[str] = None, db: Optional[AsyncSession] = None) -> bool:
        """Send welcome email after user registration."""
        if not db:
            print(f"Email not configured. Would send welcome email to {to_email}")
            return True
            
        email_config = await self._get_email_config(db)
        if not email_config:
            print(f"Email not configured in database. Would send welcome email to {to_email}")
            return True
            
        try:
            subject = "Welcome to Confab Chat!"
            
            # HTML email template
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Welcome to Confab Chat</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background-color: #10b981;
                        color: white;
                        padding: 20px;
                        text-align: center;
                        border-radius: 8px 8px 0 0;
                    }}
                    .content {{
                        background-color: #f9fafb;
                        padding: 30px;
                        border-radius: 0 0 8px 8px;
                    }}
                    .button {{
                        display: inline-block;
                        background-color: #10b981;
                        color: white;
                        padding: 12px 24px;
                        text-decoration: none;
                        border-radius: 6px;
                        margin: 20px 0;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        color: #666;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Welcome to Confab Chat!</h1>
                </div>
                <div class="content">
                    <p>Hello {user_name or 'there'},</p>
                    <p>Welcome and thank you for joining Confab Chat! Your account has been successfully created.</p>
                    <p>You can now start using our AI-powered chat platform to get answers and assistance on various topics.</p>
                    <div style="text-align: center;">
                        <a href="{await self._get_frontend_url(db)}" class="button">Start Chatting</a>
                    </div>
                    <p>If you have any questions or need help getting started, feel free to reach out to our support team.</p>
                    <p>We're excited to have you as part of our community!</p>
                </div>
                <div class="footer">
                    <p>Best regards,<br>The Confab Chat Team</p>
                </div>
            </body>
            </html>
            """
            
            # Create message
            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=html_content,
                subtype=MessageType.html,
            )
            
            # Send email
            from fastapi_mail import FastMail
            fm = FastMail(email_config)
            await fm.send_message(message)
            
            return True
            
        except ConnectionErrors as e:
            print(f"Failed to send welcome email: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error sending welcome email: {e}")
            return False
    
    async def send_invite_accepted_notification(self, admin_email: str, user_email: str, db: Optional[AsyncSession] = None) -> bool:
        """Send notification to admin when invitation is accepted."""
        if not db:
            print(f"Email not configured. Would send invite accepted notification to {admin_email}")
            return True
            
        email_config = await self._get_email_config(db)
        if not email_config:
            print(f"Email not configured in database. Would send invite accepted notification to {admin_email}")
            return True
            
        try:
            subject = "Invitation Accepted!"
            
            # HTML email template
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Invitation Accepted</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background-color: #10b981;
                        color: white;
                        padding: 20px;
                        text-align: center;
                        border-radius: 8px 8px 0 0;
                    }}
                    .content {{
                        background-color: #f9fafb;
                        padding: 30px;
                        border-radius: 0 0 8px 8px;
                    }}
                    .status-badge {{
                        display: inline-block;
                        background-color: #10b981;
                        color: white;
                        padding: 6px 12px;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                        margin: 10px 0;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        color: #666;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Invitation Accepted!</h1>
                </div>
                <div class="content">
                    <p>Hello Admin,</p>
                    <p>Great news! Your invitation has been accepted.</p>
                    <p><strong>User Email:</strong> {user_email}</p>
                    <p><strong>Status:</strong> <span class="status-badge">Accepted</span></p>
                    <p>The user has successfully created their account and can now start using Confab Chat.</p>
                    <p>You can view the updated invitation status in your admin dashboard.</p>
                </div>
                <div class="footer">
                    <p>Best regards,<br>The Confab Chat Team</p>
                </div>
            </body>
            </html>
            """
            
            # Create message
            message = MessageSchema(
                subject=subject,
                recipients=[admin_email],
                body=html_content,
                subtype=MessageType.html,
            )
            
            # Send email
            from fastapi_mail import FastMail
            fm = FastMail(email_config)
            await fm.send_message(message)
            
            return True
            
        except ConnectionErrors as e:
            print(f"Failed to send invite accepted notification: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error sending invite accepted notification: {e}")
            return False


# Global email service instance
email_service = EmailService()
