from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    app_name: str = Field(default="WhatsApp AI Bot", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Server
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # Database
    database_url: str = Field(
        default="sqlite:///./data/whatsapp_bot.db",
        alias="DATABASE_URL"
    )

    # WhatsApp Provider (twilio, meta, or waha)
    whatsapp_provider: str = Field(default="waha", alias="WHATSAPP_PROVIDER")

    # Twilio (optional if using other providers)
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_number: str = Field(default="", alias="TWILIO_WHATSAPP_NUMBER")
    twilio_webhook_url: str = Field(default="", alias="TWILIO_WEBHOOK_URL")

    # Meta WhatsApp Cloud API (optional if using other providers)
    meta_access_token: str = Field(default="", alias="META_ACCESS_TOKEN")
    meta_phone_number_id: str = Field(default="", alias="META_PHONE_NUMBER_ID")
    meta_business_account_id: str = Field(default="", alias="META_BUSINESS_ACCOUNT_ID")
    meta_webhook_verify_token: str = Field(default="", alias="META_WEBHOOK_VERIFY_TOKEN")

    # WAHA (WhatsApp HTTP API) Configuration
    waha_api_url: str = Field(default="", alias="WAHA_API_URL")
    waha_api_key: str = Field(default="", alias="WAHA_API_KEY")
    waha_session_name: str = Field(default="default", alias="WAHA_SESSION_NAME")

    # OpenAI
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4-turbo-preview", alias="OPENAI_MODEL")
    openai_max_tokens: int = Field(default=1000, alias="OPENAI_MAX_TOKENS")
    openai_temperature: float = Field(default=0.7, alias="OPENAI_TEMPERATURE")

    # Whisper (Voice Transcription)
    whisper_model: str = Field(default="whisper-1", alias="WHISPER_MODEL")

    # Vision (Image Analysis)
    vision_model: str = Field(default="gpt-4-vision-preview", alias="VISION_MODEL")
    vision_max_tokens: int = Field(default=500, alias="VISION_MAX_TOKENS")

    # User Whitelist
    whitelisted_users: str = Field(default="", alias="WHITELISTED_USERS")

    # Rate Limiting
    rate_limit_messages: int = Field(default=10, alias="RATE_LIMIT_MESSAGES")
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")

    # Conversation
    max_conversation_history: int = Field(default=10, alias="MAX_CONVERSATION_HISTORY")

    # Media Processing
    media_download_timeout: int = Field(default=30, alias="MEDIA_DOWNLOAD_TIMEOUT")
    media_max_size_mb: int = Field(default=10, alias="MEDIA_MAX_SIZE_MB")
    temp_media_dir: str = Field(default="./data/temp_media", alias="TEMP_MEDIA_DIR")

    # Security
    secret_key: str = Field(..., alias="SECRET_KEY")
    allowed_origins: str = Field(
        default="http://localhost:3000",
        alias="ALLOWED_ORIGINS"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def get_whitelisted_numbers(self) -> List[str]:
        """Parse whitelisted phone numbers"""
        if not self.whitelisted_users:
            return []
        return [num.strip() for num in self.whitelisted_users.split(",") if num.strip()]

    def get_allowed_origins_list(self) -> List[str]:
        """Parse allowed origins"""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


# Global settings instance
settings = Settings()
