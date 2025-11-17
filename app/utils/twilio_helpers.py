import hashlib
import hmac
import base64
from typing import Dict
from urllib.parse import urljoin


def verify_twilio_signature(
    url: str,
    post_params: Dict[str, str],
    signature: str,
    auth_token: str
) -> bool:
    """
    Verify that incoming request is from Twilio

    Args:
        url: The full URL of the webhook endpoint
        post_params: POST parameters from the request
        signature: X-Twilio-Signature header value
        auth_token: Twilio auth token

    Returns:
        bool: True if signature is valid
    """
    # Create the signature
    data = url
    if post_params:
        # Sort parameters and append to URL
        sorted_params = sorted(post_params.items())
        for key, value in sorted_params:
            data += key + value

    # Create HMAC-SHA1 signature
    mac = hmac.new(
        auth_token.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha1
    )
    computed_signature = base64.b64encode(mac.digest()).decode('utf-8')

    # Compare signatures
    return hmac.compare_digest(computed_signature, signature)


def extract_phone_number(whatsapp_id: str) -> str:
    """
    Extract phone number from WhatsApp ID

    Args:
        whatsapp_id: WhatsApp ID (e.g., 'whatsapp:+1234567890')

    Returns:
        str: Phone number (e.g., '+1234567890')
    """
    if whatsapp_id.startswith('whatsapp:'):
        return whatsapp_id.replace('whatsapp:', '')
    return whatsapp_id


def format_whatsapp_number(phone_number: str) -> str:
    """
    Format phone number for WhatsApp

    Args:
        phone_number: Phone number (e.g., '+1234567890')

    Returns:
        str: WhatsApp formatted number (e.g., 'whatsapp:+1234567890')
    """
    if not phone_number.startswith('whatsapp:'):
        return f'whatsapp:{phone_number}'
    return phone_number
