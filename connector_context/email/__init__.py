"""Email module for Connector Context."""

from connector_context.email.services import send_email_via_resend, send_welcome_email
from connector_context.email.templates import get_api_key_expiration_email

__all__ = [
    "send_email_via_resend",
    "send_welcome_email",
    "get_api_key_expiration_email",
]
