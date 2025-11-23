"""
Conversation Initiation API
Allows proactively starting WhatsApp conversations with specific numbers
"""

from fastapi import APIRouter, HTTPException, Header, Depends
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
import structlog

from app.models.database import MessageType, MessageDirection, get_session_local, create_db_engine, get_database_url
from app.models.crud import UserCRUD, ConversationCRUD, MessageCRUD
from app.services.waha_service import waha_service
from config.settings import settings

logger = structlog.get_logger()

router = APIRouter()

# Initialize database
engine = create_db_engine(get_database_url(settings.database_url))
SessionLocal = get_session_local(engine)


def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class InitiateConversationRequest(BaseModel):
    """Request model for initiating a conversation"""
    phone_number: str = Field(
        ...,
        description="Phone number with country code (e.g., +905551234567)",
        example="+905551234567"
    )


class InitiateConversationResponse(BaseModel):
    """Response model for conversation initiation"""
    success: bool
    message: str
    user_id: Optional[int] = None
    conversation_id: Optional[int] = None
    phone_number: Optional[str] = None
    message_id: Optional[str] = None


# Turkish greeting message for AI chatbot
GREETING_MESSAGE = """Merhaba! 👋
Ben senin için 7/24 hazır bekleyen akıllı asistanın.

Sorularını anında cevaplayabilir, ihtiyaçlarına göre öneriler sunabilir, araştırma yapabilir, hesaplamalar yapabilir, metin hazırlayabilir ve daha birçok konuda sana yardımcı olabilirim.

İster günlük işlerini kolaylaştır, ister merak ettiğin bir şeyi sor, ister profesyonel destek al — hepsi tek bir mesaj uzağında.

Hazırsan hemen başlayabilirsin:
👉 "Bugün bana nasıl yardımcı olabilirsin?" diye sorarsan sana özelliklerimi detaylıca anlatayım.

Hadi, birlikte başlayalım! 🚀"""


@router.post("/api/initiate-conversation", response_model=InitiateConversationResponse)
async def initiate_conversation(
    request: InitiateConversationRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key")
):
    """
    Proactively initiate a WhatsApp conversation with a specific phone number

    The AI will send a greeting message and be ready to handle responses.

    **Authentication:** Requires X-Api-Key header

    **Request Body:**
    - phone_number: Phone number with country code (e.g., +905551234567)

    **Returns:**
    - success: Whether the conversation was initiated successfully
    - message: Human-readable status message
    - user_id: Database ID of the user
    - conversation_id: Database ID of the conversation
    - phone_number: The phone number contacted
    - message_id: WAHA message ID if sent successfully
    """
    try:
        # Verify API key
        if not x_api_key or x_api_key != settings.secret_key:
            logger.warning("initiate_conversation_invalid_api_key")
            raise HTTPException(status_code=403, detail="Invalid API key")

        # Validate and format phone number
        phone_number = request.phone_number.strip()

        # Ensure phone number has + prefix
        if not phone_number.startswith("+"):
            phone_number = f"+{phone_number}"

        # Basic validation - phone number should have at least country code + number
        if len(phone_number) < 10:
            raise HTTPException(
                status_code=400,
                detail="Invalid phone number format. Must include country code (e.g., +905551234567)"
            )

        logger.info(
            "initiating_conversation",
            phone_number=phone_number
        )

        # Get or create user
        whitelisted_numbers = settings.get_whitelisted_numbers()
        user = UserCRUD.get_or_create_user(
            db,
            phone_number,
            whatsapp_name=None,
            whitelisted_numbers=whitelisted_numbers
        )

        # Get or create conversation
        conversation = ConversationCRUD.get_or_create_conversation(db, user.id)

        # Send greeting message via WAHA
        message_id = await waha_service.send_message(
            to_number=phone_number,
            message=GREETING_MESSAGE
        )

        if not message_id:
            logger.error(
                "initiate_conversation_send_failed",
                phone_number=phone_number,
                user_id=user.id
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to send message via WAHA. Please check WAHA service status."
            )

        # Create outgoing message record
        MessageCRUD.create_message(
            db,
            user_id=user.id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTGOING,
            message_type=MessageType.TEXT,
            content=GREETING_MESSAGE,
            twilio_message_sid=message_id,
        )

        logger.info(
            "conversation_initiated_successfully",
            phone_number=phone_number,
            user_id=user.id,
            conversation_id=conversation.id,
            message_id=message_id
        )

        return InitiateConversationResponse(
            success=True,
            message="Conversation initiated successfully",
            user_id=user.id,
            conversation_id=conversation.id,
            phone_number=phone_number,
            message_id=message_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("initiate_conversation_error", error=str(e), phone_number=request.phone_number)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/api/initiate-health")
async def initiate_health_check():
    """Health check endpoint for conversation initiation API"""
    return {
        "status": "healthy",
        "service": "conversation_initiation",
        "provider": settings.whatsapp_provider,
        "app_name": settings.app_name,
        "environment": settings.app_env
    }
