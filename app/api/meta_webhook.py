"""
Meta WhatsApp Cloud API Webhook Handler
Handles incoming messages from Meta's WhatsApp Business Platform
"""

from fastapi import APIRouter, Request, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
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


def detect_message_type_meta(message_data: Dict[str, Any]) -> MessageType:
    """Detect message type from Meta webhook data"""
    msg_type = message_data.get("type", "text")

    type_mapping = {
        "text": MessageType.TEXT,
        "image": MessageType.IMAGE,
        "audio": MessageType.AUDIO,
        "voice": MessageType.AUDIO,
        "video": MessageType.VIDEO,
        "document": MessageType.DOCUMENT,
        "location": MessageType.LOCATION,
        "contacts": MessageType.CONTACT,
    }

    return type_mapping.get(msg_type, MessageType.UNKNOWN)


@router.get("/meta-webhook")
async def meta_webhook_verification(
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """
    Webhook verification endpoint for Meta WhatsApp setup

    Meta sends GET request with verify_token to verify webhook ownership
    """
    logger.info(
        "meta_webhook_verification_attempt",
        mode=hub_mode,
        token_match=hub_verify_token == settings.meta_webhook_verify_token
    )

    # Verify the token
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_webhook_verify_token:
        logger.info("meta_webhook_verified")
        return int(hub_challenge)
    else:
        logger.warning("meta_webhook_verification_failed")
        raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/meta-webhook")
async def meta_webhook_handler(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint for receiving WhatsApp messages from Meta

    Meta sends webhook with JSON data containing message details
    """
    try:
        # Parse JSON body
        body = await request.json()

        logger.info("meta_webhook_received", body=body)

        # Meta sends multiple entries, process each
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                # Get message data
                value = change.get("value", {})

                # Check if this is a message event
                messages = value.get("messages", [])
                if not messages:
                    continue

                for message in messages:
                    await process_meta_message(message, value, db)

        return {"status": "ok"}

    except Exception as e:
        logger.error("meta_webhook_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_meta_message(message: Dict[str, Any], value: Dict[str, Any], db: Session):
    """Process individual message from Meta webhook"""
    try:
        # Extract message details
        message_id = message.get("id")
        from_number = message.get("from")  # Phone number without +
        timestamp = message.get("timestamp")

        # Check for duplicate message and delete it (for testing purposes)
        from app.models.crud import MessageCRUD
        existing_message = MessageCRUD.get_message_by_sid(db, message_id)
        if existing_message:
            logger.info(
                "duplicate_message_deleting",
                message_id=message_id,
                from_number=from_number
            )
            db.delete(existing_message)
            db.commit()

        # Add + to phone number
        from_number_formatted = f"+{from_number}"

        # Get message type and content
        msg_type = message.get("type")
        message_body = ""
        media_id = None
        media_url = None

        if msg_type == "text":
            message_body = message.get("text", {}).get("body", "")
        elif msg_type == "image":
            media_id = message.get("image", {}).get("id")
            message_body = message.get("image", {}).get("caption", "")
        elif msg_type in ["audio", "voice"]:
            media_id = message.get(msg_type, {}).get("id")
        elif msg_type == "video":
            media_id = message.get("video", {}).get("id")
            message_body = message.get("video", {}).get("caption", "")
        elif msg_type == "document":
            media_id = message.get("document", {}).get("id")
            message_body = message.get("document", {}).get("caption", "")

        # Get contact name
        contacts = value.get("contacts", [])
        whatsapp_name = contacts[0].get("profile", {}).get("name") if contacts else None

        logger.info(
            "meta_message_details",
            from_number=from_number_formatted,
            message_id=message_id,
            type=msg_type,
            has_media=bool(media_id)
        )

        # Check rate limit
        if not rate_limiter.is_allowed(from_number_formatted):
            logger.warning("rate_limit_exceeded", phone=from_number_formatted)
            return

        # Detect message type
        message_type = detect_message_type_meta(message)

        # Create message processor
        processor = MessageProcessor(db)

        # For media messages, we need to download from Meta first
        # The media_id will be used to download the actual file
        if media_id:
            # Media URL will be handled by the processor using Meta's download API
            media_url = f"meta://{media_id}"  # Special URL format to indicate Meta media

        # Process message
        await processor.process_incoming_message(
            from_number=from_number_formatted,
            message_body=message_body,
            message_type=message_type,
            media_url=media_url,
            media_content_type=msg_type if media_id else None,
            twilio_message_sid=message_id,  # Reuse field for Meta message ID
            whatsapp_name=whatsapp_name
        )

    except Exception as e:
        logger.error("meta_message_processing_error", error=str(e))


@router.get("/meta-health")
async def meta_health_check():
    """Health check endpoint for Meta webhook"""
    return {
        "status": "healthy",
        "provider": "meta",
        "app_name": settings.app_name,
        "environment": settings.app_env
    }
