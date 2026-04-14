"""Email service for sending invitations and notifications."""
import os
from typing import Optional

from fastapi_mail import ConnectionConfig, MessageSchema, MessageType
from fastapi_mail.errors import ConnectionErrors

from ..config import config


# Email configuration
email_config = ConnectionConfig(
    MAIL_USERNAME=config.SMTP_USERNAME,
    MAIL_PASSWORD=config.SMTP_PASSWORD,
    MAIL_FROM=config.FROM_EMAIL,
    MAIL_PORT=config.SMTP_PORT,
    MAIL_SERVER=config.SMTP_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)


class EmailService:
    """Email service for sending emails."""
    
    def __init__(self):
        self.config = email_config
    
    async def send_invite_email(
        self,
        to_email: str,
        invite_token: str,
        inviter_name: Optional[str] = None
    ) -> bool:
        """Send invitation email to user."""
        try:
            # Create invite link
            invite_link = f"{config.FRONTEND_URL}/accept-invite/{invite_token}"
            
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
                    .header {{
                        background-color: #4f46e5;
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
                <div class="header">
                    <h1>You're Invited!</h1>
                </div>
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
            fm = FastMail(self.config)
            await fm.send_message(message)
            
            return True
            
        except ConnectionErrors as e:
            print(f"Failed to send email: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error sending email: {e}")
            return False
    
    async def send_welcome_email(self, to_email: str, user_name: Optional[str] = None) -> bool:
        """Send welcome email after user registration."""
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
                        <a href="{config.FRONTEND_URL}" class="button">Start Chatting</a>
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
            fm = FastMail(self.config)
            await fm.send_message(message)
            
            return True
            
        except ConnectionErrors as e:
            print(f"Failed to send welcome email: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error sending welcome email: {e}")
            return False


# Global email service instance
email_service = EmailService()
