"""
WAHA (WhatsApp HTTP API) Webhook Handler
Handles incoming messages from WAHA server
"""

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import structlog

from app.models.database import MessageType, get_session_local, create_db_engine, get_database_url
from app.services.message_processor import MessageProcessor
from app.utils.rate_limiter import RateLimiter
from config.settings import settings

logger = structlog.get_logger()

router = APIRouter()

# Initialize database
engine = create_db_engine(get_database_url(settings.database_url))
SessionLocal = get_session_local(engine)

# Rate limiter
rate_limiter = RateLimiter(
    max_requests=settings.rate_limit_messages,
    window_seconds=settings.rate_limit_window_seconds
)


def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_primary_media(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the first media dict (if any) from WAHA payloads."""
    media = payload.get("media")
    if isinstance(media, dict):
        return media
    if isinstance(media, list) and media:
        for item in media:
            if isinstance(item, dict):
                return item
    return {}


def _extract_media_mimetype(payload: Dict[str, Any]) -> Optional[str]:
    media = _get_primary_media(payload)
    mimetype = media.get("mimetype") or media.get("mimeType")
    if not mimetype:
        mimetype = payload.get("mediaContentType")
    return mimetype


def _extract_media_url(payload: Dict[str, Any]) -> Optional[str]:
    media_url = payload.get("mediaUrl") or payload.get("mediaURL")
    if isinstance(media_url, str) and media_url.startswith(("http://", "https://")):
        return media_url

    media = _get_primary_media(payload)
    if media:
        url = media.get("url") or media.get("directPath")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url

    data_section = payload.get("_data") or {}
    direct_path = data_section.get("directPath")
    if isinstance(direct_path, str) and direct_path.startswith(("http://", "https://")):
        return direct_path
    return None


def detect_message_type_waha(message_data: Dict[str, Any]) -> MessageType:
    """Detect message type from WAHA webhook data"""
    msg_type = message_data.get("type")
    if not msg_type:
        msg_type = (message_data.get("_data") or {}).get("type")

    if not msg_type:
        mimetype = (_extract_media_mimetype(message_data) or "").lower()
        if mimetype.startswith("image/"):
            msg_type = "image"
        elif mimetype.startswith("audio/"):
            msg_type = "audio"
        elif mimetype.startswith("video/"):
            msg_type = "video"
        elif mimetype in ("application/pdf", "application/msword",
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
            msg_type = "document"
        elif mimetype:
            msg_type = "document"

    if not msg_type and message_data.get("hasMedia"):
        # WAHA sometimes omits type but still flags hasMedia
        msg_type = "image"

    msg_type = (msg_type or "chat").lower()

    type_mapping = {
        "chat": MessageType.TEXT,
        "text": MessageType.TEXT,
        "image": MessageType.IMAGE,
        "audio": MessageType.AUDIO,
        "voice": MessageType.AUDIO,
        "ptt": MessageType.AUDIO,  # Push-to-talk
        "video": MessageType.VIDEO,
        "document": MessageType.DOCUMENT,
        "location": MessageType.LOCATION,
        "vcard": MessageType.CONTACT,
    }

    return type_mapping.get(msg_type, MessageType.UNKNOWN)


@router.post("/waha-webhook")
async def waha_webhook_handler(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key")
):
    """
    Webhook endpoint for receiving WhatsApp messages from WAHA

    WAHA sends webhook with JSON data containing message details
    """
    try:
        # Verify API key if configured
        if settings.waha_api_key and x_api_key != settings.waha_api_key:
            logger.warning("waha_webhook_invalid_api_key")
            raise HTTPException(status_code=403, detail="Invalid API key")

        # Parse JSON body
        body = await request.json()

        logger.info("waha_webhook_received", body=body)

        # WAHA webhook structure
        event = body.get("event")
        session = body.get("session")
        payload = body.get("payload", {})

        # Only process message events
        if event != "message":
            logger.info("waha_webhook_skipped_non_message_event", event_type=event)
            return {"status": "ok", "message": "Event ignored"}

        # Check if this is an incoming message (not from us)
        if payload.get("fromMe", False):
            logger.info("waha_webhook_skipped_own_message")
            return {"status": "ok", "message": "Own message ignored"}

        await process_waha_message(payload, session, db)

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("waha_webhook_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_waha_message(payload: Dict[str, Any], session: str, db: Session):
    """Process individual message from WAHA webhook"""
    try:
        # Extract message details
        message_id = payload.get("id")
        from_number = payload.get("from")  # Format: 1234567890@c.us
        timestamp = payload.get("timestamp")

        # Extract phone number from chatId format (remove @c.us or @g.us)
        if "@" in from_number:
            phone_only = from_number.split("@")[0]
        else:
            phone_only = from_number

        # Add + to phone number
        from_number_formatted = f"+{phone_only}"

        # Check for duplicate message and delete it (for testing purposes)
        from app.models.crud import MessageCRUD
        existing_message = MessageCRUD.get_message_by_sid(db, message_id)
        if existing_message:
            logger.info(
                "duplicate_message_deleting",
                message_id=message_id,
                from_number=from_number_formatted
            )
            db.delete(existing_message)
            db.commit()

        # Detect message type and prepare content
        message_type = detect_message_type_waha(payload)
        message_body = ""
        media_url = None
        media_content_type = None

        if message_type == MessageType.TEXT:
            message_body = payload.get("body", "")
        elif message_type == MessageType.IMAGE:
            media_url = _extract_media_url(payload)
            message_body = payload.get("caption") or payload.get("body", "")
            media_content_type = _extract_media_mimetype(payload) or "image/jpeg"
        elif message_type in [MessageType.AUDIO]:
            media_url = _extract_media_url(payload)
            media_content_type = _extract_media_mimetype(payload) or "audio/ogg"
        elif message_type == MessageType.VIDEO:
            media_url = _extract_media_url(payload)
            message_body = payload.get("caption") or ""
            media_content_type = _extract_media_mimetype(payload) or "video/mp4"
        elif message_type == MessageType.DOCUMENT:
            media_url = _extract_media_url(payload)
            message_body = payload.get("caption") or ""
            media_content_type = _extract_media_mimetype(payload) or "application/octet-stream"
        else:
            message_body = payload.get("body", "")

        # Get contact name
        contact_name = payload.get("_data", {}).get("notifyName") or payload.get("author")

        logger.info(
            "waha_message_details",
            from_number=from_number_formatted,
            message_id=message_id,
            type=message_type.value if isinstance(message_type, MessageType) else str(message_type),
            has_media=bool(media_url)
        )

        # Check rate limit
        if not rate_limiter.is_allowed(from_number_formatted):
            logger.warning("rate_limit_exceeded", phone=from_number_formatted)
            return

        # Create message processor
        processor = MessageProcessor(db)

        # Process message
        await processor.process_incoming_message(
            from_number=from_number_formatted,
            message_body=message_body,
            message_type=message_type,
            media_url=media_url,
            media_content_type=media_content_type,
            twilio_message_sid=message_id,  # Reuse field for WAHA message ID
            whatsapp_name=contact_name,
            waha_chat_id=from_number  # Pass original chat ID with suffix (@lid or @c.us)
        )

    except Exception as e:
        logger.error("waha_message_processing_error", error=str(e))


@router.get("/waha-health")
async def waha_health_check():
    """Health check endpoint for WAHA webhook"""
    return {
        "status": "healthy",
        "provider": "waha",
        "app_name": settings.app_name,
        "environment": settings.app_env
    }
