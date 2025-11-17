import logging
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.webhook import router as webhook_router
from app.api.meta_webhook import router as meta_webhook_router
from app.models.database import create_db_engine, init_database, get_database_url
from config.settings import settings


# Configure structured logging
logging.basicConfig(
    format="%(message)s",
    level=getattr(logging, settings.log_level.upper(), logging.INFO)
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info(
        "application_starting",
        app_name=settings.app_name,
        environment=settings.app_env
    )

    # Initialize database
    try:
        engine = create_db_engine(get_database_url(settings.database_url))
        init_database(engine)
        logger.info("database_initialized", url=settings.database_url)
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        raise

    # Validate configuration
    try:
        # Check Twilio credentials
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            logger.warning("twilio_credentials_missing")

        # Check OpenAI credentials
        if not settings.openai_api_key:
            logger.warning("openai_credentials_missing")

        logger.info("configuration_validated")
    except Exception as e:
        logger.error("configuration_validation_failed", error=str(e))

    yield

    # Shutdown
    logger.info("application_shutting_down")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="WhatsApp AI Bot powered by OpenAI and Twilio",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook_router, tags=["Twilio Webhook"])
app.include_router(meta_webhook_router, tags=["Meta Webhook"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "status": "running",
        "environment": settings.app_env
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
