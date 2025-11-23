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


def detect_message_type_waha(message_data: Dict[str, Any]) -> MessageType:
    """Detect message type from WAHA webhook data"""
    msg_type = message_data.get("type", "chat")

    type_mapping = {
        "chat": MessageType.TEXT,
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

        # Get message type and content
        msg_type = payload.get("type", "chat")
        message_body = ""
        media_url = None
        media_content_type = None

        # Extract message content based on type
        if msg_type == "chat":
            message_body = payload.get("body", "")
        elif msg_type == "image":
            media_url = payload.get("mediaUrl") or payload.get("media", {}).get("url")
            message_body = payload.get("caption", "")
            media_content_type = "image"
        elif msg_type in ["audio", "voice", "ptt"]:
            media_url = payload.get("mediaUrl") or payload.get("media", {}).get("url")
            media_content_type = "audio"
        elif msg_type == "video":
            media_url = payload.get("mediaUrl") or payload.get("media", {}).get("url")
            message_body = payload.get("caption", "")
            media_content_type = "video"
        elif msg_type == "document":
            media_url = payload.get("mediaUrl") or payload.get("media", {}).get("url")
            message_body = payload.get("caption", "")
            media_content_type = "document"

        # Get contact name
        contact_name = payload.get("_data", {}).get("notifyName") or payload.get("author")

        logger.info(
            "waha_message_details",
            from_number=from_number_formatted,
            message_id=message_id,
            type=msg_type,
            has_media=bool(media_url)
        )

        # Check rate limit
        if not rate_limiter.is_allowed(from_number_formatted):
            logger.warning("rate_limit_exceeded", phone=from_number_formatted)
            return

        # Detect message type
        message_type = detect_message_type_waha(payload)

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
