"""
Meta WhatsApp Cloud API Service
Official WhatsApp Business Platform API integration
"""

from typing import Optional, Dict, Any
import httpx
import structlog

from config.settings import settings

logger = structlog.get_logger()


class MetaWhatsAppService:
    """Service for Meta WhatsApp Cloud API interactions"""

    def __init__(self):
        self.api_version = "v21.0"  # Latest as of Nov 2025
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        self.phone_number_id = settings.meta_phone_number_id
        self.access_token = settings.meta_access_token

    async def send_message(
        self,
        to_number: str,
        message: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Send WhatsApp message via Meta Cloud API

        Args:
            to_number: Recipient phone number (with country code, no +)
            message: Message text
            media_url: Optional media URL to send
            media_type: Type of media (image, audio, document, video)

        Returns:
            Message ID if successful, None otherwise
        """
        try:
            # Clean phone number (remove + and spaces)
            clean_number = to_number.replace("+", "").replace(" ", "").replace("-", "")

            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            # Build message payload
            if media_url and media_type:
                # Send media message
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": clean_number,
                    "type": media_type,
                    media_type: {
                        "link": media_url,
                        "caption": message if message else None
                    }
                }
            else:
                # Send text message
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": clean_number,
                    "type": "text",
                    "text": {
                        "preview_url": False,
                        "body": message
                    }
                }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                result = response.json()
                message_id = result.get("messages", [{}])[0].get("id")

                logger.info(
                    "meta_message_sent",
                    to=clean_number,
                    message_id=message_id,
                    has_media=bool(media_url)
                )

                return message_id

        except Exception as e:
            logger.error(
                "meta_message_send_error",
                error=str(e),
                to=to_number
            )
            return None

    async def download_media(self, media_id: str) -> Optional[bytes]:
        """
        Download media from Meta servers

        Args:
            media_id: Media ID from webhook

        Returns:
            Media content as bytes or None if failed
        """
        try:
            # Step 1: Get media URL
            url = f"{self.base_url}/{media_id}"
            headers = {"Authorization": f"Bearer {self.access_token}"}

            async with httpx.AsyncClient() as client:
                # Get media metadata
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                media_data = response.json()

                media_url = media_data.get("url")
                if not media_url:
                    logger.error("meta_media_no_url", media_id=media_id)
                    return None

                # Step 2: Download actual media
                media_response = await client.get(media_url, headers=headers)
                media_response.raise_for_status()

                logger.info(
                    "meta_media_downloaded",
                    media_id=media_id,
                    size_bytes=len(media_response.content)
                )

                return media_response.content

        except Exception as e:
            logger.error("meta_media_download_error", error=str(e), media_id=media_id)
            return None

    async def mark_message_read(self, message_id: str) -> bool:
        """
        Mark message as read

        Args:
            message_id: Message ID to mark as read

        Returns:
            True if successful
        """
        try:
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                logger.info("message_marked_read", message_id=message_id)
                return True

        except Exception as e:
            logger.error("mark_read_error", error=str(e), message_id=message_id)
            return False


# Global instance
meta_whatsapp_service = MetaWhatsAppService()
