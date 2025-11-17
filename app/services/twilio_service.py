from typing import Optional
from twilio.rest import Client
import structlog

from config.settings import settings
from app.utils.twilio_helpers import format_whatsapp_number

logger = structlog.get_logger()


class TwilioService:
    """Service for Twilio WhatsApp API interactions"""

    def __init__(self):
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self.from_number = settings.twilio_whatsapp_number

    async def send_message(
        self,
        to_number: str,
        message: str,
        media_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Send WhatsApp message via Twilio

        Args:
            to_number: Recipient phone number
            message: Message text
            media_url: Optional media URL to send with message

        Returns:
            Message SID if successful, None otherwise
        """
        try:
            # Format numbers for WhatsApp
            to_whatsapp = format_whatsapp_number(to_number)

            # Prepare message parameters
            params = {
                'from_': self.from_number,
                'to': to_whatsapp,
                'body': message
            }

            # Add media if provided
            if media_url:
                params['media_url'] = [media_url]

            # Send message
            twilio_message = self.client.messages.create(**params)

            logger.info(
                "message_sent",
                to=to_number,
                message_sid=twilio_message.sid,
                status=twilio_message.status,
                has_media=bool(media_url)
            )

            return twilio_message.sid

        except Exception as e:
            logger.error(
                "message_send_error",
                error=str(e),
                to=to_number
            )
            return None

    async def get_message_status(self, message_sid: str) -> Optional[str]:
        """
        Get status of sent message

        Args:
            message_sid: Twilio message SID

        Returns:
            Message status or None if failed
        """
        try:
            message = self.client.messages(message_sid).fetch()
            return message.status
        except Exception as e:
            logger.error("message_status_error", error=str(e), sid=message_sid)
            return None

    async def download_media(self, media_url: str) -> Optional[bytes]:
        """
        Download media from Twilio

        Args:
            media_url: Twilio media URL

        Returns:
            Media content as bytes or None if failed
        """
        try:
            # Twilio media URLs require authentication
            import httpx
            auth = (settings.twilio_account_sid, settings.twilio_auth_token)

            async with httpx.AsyncClient() as client:
                response = await client.get(media_url, auth=auth)
                response.raise_for_status()

                logger.info(
                    "media_downloaded_from_twilio",
                    size_bytes=len(response.content)
                )

                return response.content

        except Exception as e:
            logger.error("twilio_media_download_error", error=str(e), url=media_url)
            return None


# Global instance
twilio_service = TwilioService()
