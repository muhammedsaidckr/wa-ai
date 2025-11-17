from fastapi import APIRouter, Request, Form, HTTPException, Header, Depends
from typing import Optional
from sqlalchemy.orm import Session
import structlog

from app.models.database import MessageType, get_session_local, create_db_engine, get_database_url
from app.services.message_processor import MessageProcessor
from app.utils.twilio_helpers import verify_twilio_signature, extract_phone_number
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


def detect_message_type(num_media: int, media_content_type: Optional[str]) -> MessageType:
    """Detect message type from Twilio webhook data"""
    if num_media == 0:
        return MessageType.TEXT

    if media_content_type:
        if media_content_type.startswith('image/'):
            return MessageType.IMAGE
        elif media_content_type.startswith('audio/'):
            return MessageType.AUDIO
        elif media_content_type.startswith('video/'):
            return MessageType.VIDEO
        elif media_content_type == 'application/pdf' or 'document' in media_content_type:
            return MessageType.DOCUMENT

    return MessageType.UNKNOWN


@router.get("/webhook")
async def webhook_verification(request: Request):
    """
    Webhook verification endpoint for Twilio setup
    """
    return {"status": "ok", "message": "WhatsApp webhook is active"}


@router.post("/webhook")
async def webhook_handler(
    request: Request,
    db: Session = Depends(get_db),
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(default=""),
    NumMedia: int = Form(default=0),
    MediaUrl0: Optional[str] = Form(default=None),
    MediaContentType0: Optional[str] = Form(default=None),
    ProfileName: Optional[str] = Form(default=None),
    x_twilio_signature: Optional[str] = Header(default=None, alias="X-Twilio-Signature")
):
    """
    Webhook endpoint for receiving WhatsApp messages from Twilio

    Twilio sends webhook with form data containing message details
    """
    try:
        # Get request URL for signature verification
        url = str(request.url)

        # Get form data for signature verification
        form_data = await request.form()
        post_params = dict(form_data)

        # Verify Twilio signature (in production, this should be enforced)
        if x_twilio_signature and settings.app_env == "production":
            is_valid = verify_twilio_signature(
                url,
                post_params,
                x_twilio_signature,
                settings.twilio_auth_token
            )
            if not is_valid:
                logger.warning("invalid_twilio_signature", url=url)
                raise HTTPException(status_code=403, detail="Invalid signature")

        # Extract phone number
        from_number = extract_phone_number(From)

        logger.info(
            "webhook_received",
            from_number=from_number,
            message_sid=MessageSid,
            num_media=NumMedia
        )

        # Check rate limit
        if not rate_limiter.is_allowed(from_number):
            logger.warning("rate_limit_exceeded", phone=from_number)
            return {"status": "rate_limited"}

        # Detect message type
        message_type = detect_message_type(NumMedia, MediaContentType0)

        # Create message processor
        processor = MessageProcessor(db)

        # Process message asynchronously
        await processor.process_incoming_message(
            from_number=from_number,
            message_body=Body,
            message_type=message_type,
            media_url=MediaUrl0,
            media_content_type=MediaContentType0,
            twilio_message_sid=MessageSid,
            whatsapp_name=ProfileName
        )

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("webhook_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "environment": settings.app_env
    }
