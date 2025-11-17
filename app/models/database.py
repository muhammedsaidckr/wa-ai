from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import enum

Base = declarative_base()


class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACT = "contact"
    UNKNOWN = "unknown"


class MessageDirection(str, enum.Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    whatsapp_name = Column(String(255), nullable=True)
    is_whitelisted = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, phone={self.phone_number}, whitelisted={self.is_whitelisted})>"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation(id={self.id}, user_id={self.user_id}, active={self.is_active})>"


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)

    # Message metadata
    twilio_message_sid = Column(String(100), unique=True, index=True, nullable=True)
    direction = Column(Enum(MessageDirection), nullable=False)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT)

    # Message content
    content = Column(Text, nullable=True)  # Text content or transcribed text
    media_url = Column(String(500), nullable=True)  # URL of media file
    media_content_type = Column(String(100), nullable=True)

    # AI processing
    ai_response = Column(Text, nullable=True)
    ai_model_used = Column(String(100), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    # Status
    is_processed = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="messages")
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, type={self.message_type}, direction={self.direction})>"


# Database session management
def get_database_url(db_url: str = None) -> str:
    """Get database URL from environment or use default"""
    if db_url:
        return db_url
    return "sqlite:///./data/whatsapp_bot.db"


def create_db_engine(database_url: str):
    """Create database engine"""
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
        echo=False
    )


def init_database(engine):
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_session_local(engine):
    """Get session maker"""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
