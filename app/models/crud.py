from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .database import User, Message, Conversation, MessageType, MessageDirection


class UserCRUD:
    """CRUD operations for User model"""

    @staticmethod
    def create_user(db: Session, phone_number: str, whatsapp_name: str = None, is_whitelisted: bool = False) -> User:
        """Create a new user"""
        user = User(
            phone_number=phone_number,
            whatsapp_name=whatsapp_name,
            is_whitelisted=is_whitelisted
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_user_by_phone(db: Session, phone_number: str) -> Optional[User]:
        """Get user by phone number"""
        return db.query(User).filter(User.phone_number == phone_number).first()

    @staticmethod
    def get_or_create_user(db: Session, phone_number: str, whatsapp_name: str = None, whitelisted_numbers: List[str] = None) -> User:
        """Get existing user or create new one"""
        user = UserCRUD.get_user_by_phone(db, phone_number)
        if not user:
            is_whitelisted = phone_number in (whitelisted_numbers or [])
            user = UserCRUD.create_user(db, phone_number, whatsapp_name, is_whitelisted)
        return user

    @staticmethod
    def update_user(db: Session, user_id: int, **kwargs) -> Optional[User]:
        """Update user details"""
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)
        return user


class ConversationCRUD:
    """CRUD operations for Conversation model"""

    @staticmethod
    def create_conversation(db: Session, user_id: int, title: str = None) -> Conversation:
        """Create a new conversation"""
        conversation = Conversation(
            user_id=user_id,
            title=title or f"Conversation {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    @staticmethod
    def get_active_conversation(db: Session, user_id: int) -> Optional[Conversation]:
        """Get user's active conversation"""
        return db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.is_active == True
        ).order_by(desc(Conversation.updated_at)).first()

    @staticmethod
    def get_or_create_conversation(db: Session, user_id: int) -> Conversation:
        """Get active conversation or create new one"""
        conversation = ConversationCRUD.get_active_conversation(db, user_id)
        if not conversation:
            conversation = ConversationCRUD.create_conversation(db, user_id)
        return conversation


class MessageCRUD:
    """CRUD operations for Message model"""

    @staticmethod
    def create_message(
        db: Session,
        user_id: int,
        conversation_id: int,
        direction: MessageDirection,
        message_type: MessageType = MessageType.TEXT,
        content: str = None,
        media_url: str = None,
        media_content_type: str = None,
        twilio_message_sid: str = None
    ) -> Message:
        """Create a new message"""
        message = Message(
            user_id=user_id,
            conversation_id=conversation_id,
            direction=direction,
            message_type=message_type,
            content=content,
            media_url=media_url,
            media_content_type=media_content_type,
            twilio_message_sid=twilio_message_sid
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

    @staticmethod
    def update_message(db: Session, message_id: int, **kwargs) -> Optional[Message]:
        """Update message details"""
        message = db.query(Message).filter(Message.id == message_id).first()
        if message:
            for key, value in kwargs.items():
                if hasattr(message, key):
                    setattr(message, key, value)
            db.commit()
            db.refresh(message)
        return message

    @staticmethod
    def mark_as_processed(
        db: Session,
        message_id: int,
        ai_response: str = None,
        ai_model: str = None,
        prompt_tokens: int = None,
        completion_tokens: int = None,
        error_message: str = None
    ) -> Optional[Message]:
        """Mark message as processed with AI response"""
        return MessageCRUD.update_message(
            db,
            message_id,
            is_processed=True,
            processed_at=datetime.utcnow(),
            ai_response=ai_response,
            ai_model_used=ai_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error_message=error_message
        )

    @staticmethod
    def get_conversation_history(
        db: Session,
        conversation_id: int,
        limit: int = 10
    ) -> List[Message]:
        """Get recent messages from conversation"""
        return db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(desc(Message.created_at)).limit(limit).all()

    @staticmethod
    def get_message_by_sid(db: Session, message_sid: str) -> Optional[Message]:
        """Get message by Twilio SID"""
        return db.query(Message).filter(Message.twilio_message_sid == message_sid).first()
