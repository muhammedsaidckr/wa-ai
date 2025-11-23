"""
WAHA (WhatsApp HTTP API) Service
Integration with WAHA server for WhatsApp messaging
"""

from typing import Optional, Dict, Any
import asyncio
import random
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

    def _get_chat_id(self, phone_number: str) -> str:
        """
        Convert phone number to WAHA chat ID format

        Args:
            phone_number: Phone number with country code

        Returns:
            Chat ID in format: number@c.us
        """
        # Clean phone number (remove + and spaces, keep numbers only)
        clean_number = phone_number.replace("+", "").replace(" ", "").replace("-", "")
        return f"{clean_number}@c.us"

    async def send_seen(self, to_number: str, chat_id: Optional[str] = None) -> bool:
        """
        Mark messages as seen (read)

        Args:
            to_number: Recipient phone number (with country code)
            chat_id: Optional WAHA chat ID with suffix. If not provided, will be constructed from to_number

        Returns:
            True if successful, False otherwise
        """
        try:
            if not chat_id:
                chat_id = self._get_chat_id(to_number)
            url = f"{self.api_url}/api/sendSeen"
            headers = self._get_headers()

            payload = {
                "session": self.session_name,
                "chatId": chat_id,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code not in [200, 201]:
                    logger.warning(
                        "waha_send_seen_failed",
                        status_code=response.status_code,
                        to=chat_id,
                    )
                    return False

                logger.debug("waha_send_seen_success", to=chat_id)
                return True

        except Exception as e:
            logger.error("waha_send_seen_error", error=str(e), to=to_number)
            return False

    async def start_typing(self, to_number: str, chat_id: Optional[str] = None) -> bool:
        """
        Start typing indicator

        Args:
            to_number: Recipient phone number (with country code)
            chat_id: Optional WAHA chat ID with suffix. If not provided, will be constructed from to_number

        Returns:
            True if successful, False otherwise
        """
        try:
            if not chat_id:
                chat_id = self._get_chat_id(to_number)
            url = f"{self.api_url}/api/startTyping"
            headers = self._get_headers()

            payload = {
                "session": self.session_name,
                "chatId": chat_id,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code not in [200, 201]:
                    logger.warning(
                        "waha_start_typing_failed",
                        status_code=response.status_code,
                        to=chat_id,
                    )
                    return False

                logger.debug("waha_start_typing_success", to=chat_id)
                return True

        except Exception as e:
            logger.error("waha_start_typing_error", error=str(e), to=to_number)
            return False

    async def stop_typing(self, to_number: str, chat_id: Optional[str] = None) -> bool:
        """
        Stop typing indicator

        Args:
            to_number: Recipient phone number (with country code)
            chat_id: Optional WAHA chat ID with suffix. If not provided, will be constructed from to_number

        Returns:
            True if successful, False otherwise
        """
        try:
            if not chat_id:
                chat_id = self._get_chat_id(to_number)
            url = f"{self.api_url}/api/stopTyping"
            headers = self._get_headers()

            payload = {
                "session": self.session_name,
                "chatId": chat_id,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code not in [200, 201]:
                    logger.warning(
                        "waha_stop_typing_failed",
                        status_code=response.status_code,
                        to=chat_id,
                    )
                    return False

                logger.debug("waha_stop_typing_success", to=chat_id)
                return True

        except Exception as e:
            logger.error("waha_stop_typing_error", error=str(e), to=to_number)
            return False

    async def send_message(
        self,
        to_number: str,
        message: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        waha_chat_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send WhatsApp message via WAHA API

        Implements anti-spam flow:
        1. Send 'seen' status
        2. Start typing indicator
        3. Wait realistic delay based on message length
        4. Stop typing indicator
        5. Send message

        Args:
            to_number: Recipient phone number (with country code)
            message: Message text
            media_url: Optional media URL to send
            media_type: Type of media (image, audio, document, video)
            waha_chat_id: Original WAHA chat ID with suffix (e.g., @lid or @c.us). If not provided, will be constructed from to_number

        Returns:
            Message ID if successful, None otherwise
        """
        try:
            # Get chat ID - use provided one or construct from phone number
            chat_id = waha_chat_id if waha_chat_id else self._get_chat_id(to_number)

            # Step 1: Send 'seen' status
            await self.send_seen(to_number, chat_id=chat_id)

            # Step 2: Start typing indicator
            await self.start_typing(to_number, chat_id=chat_id)

            # Step 3: Calculate realistic typing delay
            # Base delay: 50-100ms per character
            # Min: 1 second, Max: 5 seconds
            message_length = len(message) if message else 0
            base_delay = message_length * random.uniform(0.05, 0.1)
            typing_delay = max(1.0, min(5.0, base_delay))

            logger.debug(
                "waha_typing_delay",
                to=chat_id,
                message_length=message_length,
                delay_seconds=typing_delay,
            )

            # Wait to simulate realistic typing
            await asyncio.sleep(typing_delay)

            # Step 4: Stop typing indicator
            await self.stop_typing(to_number, chat_id=chat_id)

            # Step 5: Send the actual message
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
