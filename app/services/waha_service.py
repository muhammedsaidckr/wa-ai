"""
WAHA (WhatsApp HTTP API) Service
Integration with WAHA server for WhatsApp messaging
"""

from typing import Optional, Dict, Any
import httpx
import structlog

from config.settings import settings

logger = structlog.get_logger()


class WAHAService:
    """Service for WAHA (WhatsApp HTTP API) interactions"""

    def __init__(self):
        self.api_url = settings.waha_api_url.rstrip('/')
        self.api_key = settings.waha_api_key
        self.session_name = settings.waha_session_name

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for WAHA API requests"""
        return {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def send_message(
        self,
        to_number: str,
        message: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send WhatsApp message via WAHA API

        Args:
            to_number: Recipient phone number (with country code)
            message: Message text
            media_url: Optional media URL to send
            media_type: Type of media (image, audio, document, video)

        Returns:
            Message ID if successful, None otherwise
        """
        try:
            # Clean phone number (remove + and spaces, keep numbers only)
            clean_number = to_number.replace("+", "").replace(" ", "").replace("-", "")
            # WAHA expects chatId in format: number@c.us
            chat_id = f"{clean_number}@c.us"

            url = f"{self.api_url}/api/sendText"
            headers = self._get_headers()

            # Build message payload based on whether media is included
            if media_url and media_type:
                # Send media message
                # Map message types to WAHA endpoints
                media_endpoints = {
                    "image": "/api/sendImage",
                    "audio": "/api/sendAudio",
                    "video": "/api/sendVideo",
                    "document": "/api/sendFile",
                }

                endpoint = media_endpoints.get(media_type, "/api/sendFile")
                url = f"{self.api_url}{endpoint}"

                payload = {
                    "session": self.session_name,
                    "chatId": chat_id,
                    "file": {
                        "url": media_url
                    },
                    "caption": message if message else "",
                }
            else:
                # Send text message
                payload = {
                    "session": self.session_name,
                    "chatId": chat_id,
                    "text": message,
                }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code not in [200, 201]:
                    error_detail = response.text
                    logger.error(
                        "waha_api_error",
                        status_code=response.status_code,
                        error_detail=error_detail,
                        to=chat_id,
                        payload=payload,
                    )
                    return None

                response.raise_for_status()

                result = response.json()
                message_id = result.get("id")

                logger.info(
                    "waha_message_sent",
                    to=chat_id,
                    message_id=message_id,
                    has_media=bool(media_url),
                )

                return message_id

        except Exception as e:
            logger.error("waha_message_send_error", error=str(e), to=to_number)
            return None

    async def download_media(self, media_url: str) -> Optional[bytes]:
        """
        Download media from WAHA server

        Args:
            media_url: Media URL from WAHA webhook

        Returns:
            Media content as bytes or None if failed
        """
        try:
            headers = self._get_headers()

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(media_url, headers=headers)
                response.raise_for_status()

                logger.info(
                    "waha_media_downloaded",
                    media_url=media_url,
                    size_bytes=len(response.content),
                )

                return response.content

        except Exception as e:
            logger.error("waha_media_download_error", error=str(e), media_url=media_url)
            return None

    async def get_session_status(self) -> Optional[Dict[str, Any]]:
        """
        Get WAHA session status

        Returns:
            Session status information or None if failed
        """
        try:
            url = f"{self.api_url}/api/sessions/{self.session_name}"
            headers = self._get_headers()

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                result = response.json()
                logger.info("waha_session_status", status=result.get("status"))
                return result

        except Exception as e:
            logger.error("waha_session_status_error", error=str(e))
            return None


# Global instance
waha_service = WAHAService()
