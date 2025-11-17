# WhatsApp AI Bot

A sophisticated WhatsApp chatbot powered by OpenAI's GPT models and Twilio's WhatsApp API. The bot can process text messages, analyze images, transcribe voice messages, and extract information from documents.

## Features

- **Text Conversations**: Natural language conversations using OpenAI GPT models
- **Image Analysis**: Analyze and describe images using GPT-4 Vision
- **Voice Transcription**: Convert voice messages to text using Whisper API
- **Document Processing**: Extract and summarize text from PDF documents
- **User Whitelist**: Control access with phone number whitelisting
- **Rate Limiting**: Prevent abuse with configurable rate limits
- **Conversation History**: Maintain context across multiple messages
- **Docker Support**: Easy deployment with Docker and docker-compose

## Architecture

The system follows a clean, modular architecture:

```
User (WhatsApp) → Twilio WhatsApp API → Webhook Endpoint → Message Processing → AI Service → Response Handler → Twilio → User
```

### Components

1. **FastAPI Application**: Webhook endpoint with signature verification
2. **Message Processing Layer**: Handles whitelist, message types, context, and rate limiting
3. **AI Service**: OpenAI integration for text, vision, and voice processing
4. **Media Processing**: Downloads and processes images, audio, and documents
5. **Database Layer**: SQLite/PostgreSQL for storing users, conversations, and messages
6. **Response Handler**: Formats and sends responses via Twilio

## Prerequisites

- Python 3.11+
- Twilio account with WhatsApp enabled
- OpenAI API key
- Docker and Docker Compose (for containerized deployment)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd backend
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# User Whitelist (comma-separated phone numbers with country code)
WHITELISTED_USERS=+1234567890,+9876543210

# Security
SECRET_KEY=generate-a-secure-random-string-here
```

### 5. Initialize Database

The database will be automatically initialized on first run. By default, it uses SQLite stored in `./data/whatsapp_bot.db`.

## Running the Application

### Local Development

```bash
python main.py
```

The application will start on `http://localhost:8000`.

### Using Docker

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

## Twilio Webhook Configuration

1. **Expose your local server** (for development):
   ```bash
   # Using ngrok
   ngrok http 8000
   ```

2. **Configure Twilio Webhook**:
   - Go to [Twilio Console](https://console.twilio.com/)
   - Navigate to Messaging → Settings → WhatsApp sandbox settings
   - Set "When a message comes in" to: `https://your-domain.com/webhook`
   - Set HTTP method to: `POST`
   - Save configuration

3. **Test the webhook**:
   - Send a message to your Twilio WhatsApp number
   - Check the logs for incoming webhook requests

## API Endpoints

### Webhook Endpoints

- `GET /webhook` - Webhook verification
- `POST /webhook` - Receive WhatsApp messages from Twilio

### Health & Status

- `GET /` - Root endpoint with app info
- `GET /health` - Health check endpoint

### API Documentation

FastAPI automatically generates interactive API documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Application name | WhatsApp AI Bot |
| `APP_ENV` | Environment (development/production) | development |
| `DEBUG` | Enable debug mode | True |
| `HOST` | Server host | 0.0.0.0 |
| `PORT` | Server port | 8000 |
| `DATABASE_URL` | Database connection string | sqlite:///./data/whatsapp_bot.db |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Required |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | Required |
| `TWILIO_WHATSAPP_NUMBER` | Your Twilio WhatsApp number | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL` | GPT model to use | gpt-4-turbo-preview |
| `WHITELISTED_USERS` | Comma-separated phone numbers | Empty |
| `RATE_LIMIT_MESSAGES` | Max messages per window | 10 |
| `RATE_LIMIT_WINDOW_SECONDS` | Rate limit window | 60 |
| `MAX_CONVERSATION_HISTORY` | Messages to include in context | 10 |

### User Whitelist

Add phone numbers to the whitelist in your `.env` file:

```env
WHITELISTED_USERS=+1234567890,+9876543210,+1122334455
```

Phone numbers must include the country code with a `+` prefix.

## Project Structure

```
backend/
├── app/
│   ├── api/
│   │   └── webhook.py          # Webhook endpoints
│   ├── models/
│   │   ├── database.py         # SQLAlchemy models
│   │   └── crud.py             # Database operations
│   ├── services/
│   │   ├── openai_service.py   # OpenAI integration
│   │   ├── twilio_service.py   # Twilio integration
│   │   ├── media_service.py    # Media processing
│   │   └── message_processor.py # Message orchestration
│   └── utils/
│       ├── twilio_helpers.py   # Twilio utilities
│       └── rate_limiter.py     # Rate limiting
├── config/
│   └── settings.py             # Configuration management
├── data/                       # SQLite database and temp files
├── tests/                      # Test files
├── main.py                     # Application entry point
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
├── docker-compose.yml          # Docker Compose configuration
└── README.md                   # This file
```

## Message Processing Flow

1. **Webhook receives message** from Twilio
2. **Signature verification** ensures request is from Twilio
3. **Rate limiting** checks if user exceeded limits
4. **User whitelist** verification
5. **Message type detection** (text, image, audio, document)
6. **Database record creation** for incoming message
7. **AI processing** based on message type:
   - Text: GPT conversation
   - Image: Vision API analysis
   - Audio: Whisper transcription + GPT response
   - Document: Text extraction + GPT summary
8. **Response generation** and sending via Twilio
9. **Database update** with AI response and metrics

## Database Schema

### Users
- `id`, `phone_number`, `whatsapp_name`, `is_whitelisted`, `is_active`, timestamps

### Conversations
- `id`, `user_id`, `title`, `is_active`, timestamps

### Messages
- `id`, `user_id`, `conversation_id`, `direction`, `message_type`
- `content`, `media_url`, `media_content_type`
- `ai_response`, `ai_model_used`, token counts
- `is_processed`, `error_message`, timestamps

## Troubleshooting

### Webhook Not Receiving Messages

1. Check Twilio webhook configuration
2. Verify your server is publicly accessible
3. Check Twilio debugger: https://console.twilio.com/debugger
4. Review application logs for errors

### OpenAI API Errors

1. Verify API key is valid
2. Check OpenAI account has credits
3. Review rate limits and quotas
4. Check model availability

### Database Issues

1. Ensure `./data` directory exists and is writable
2. Check database file permissions
3. Review logs for SQLAlchemy errors

### Docker Issues

1. Ensure `.env` file exists
2. Check Docker logs: `docker-compose logs -f`
3. Verify port 8000 is not in use
4. Check volume mounts and permissions

## Security Considerations

1. **Never commit `.env` file** to version control
2. **Use strong SECRET_KEY** in production
3. **Enable signature verification** in production
4. **Use HTTPS** for webhook endpoint
5. **Implement user whitelist** to control access
6. **Set appropriate rate limits**
7. **Keep dependencies updated**

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
# Format code
black .

# Lint code
flake8 .
```

## Production Deployment

### VPS Deployment

1. Set up a VPS with Docker installed
2. Clone repository and configure `.env`
3. Run with docker-compose:
   ```bash
   docker-compose up -d
   ```
4. Configure reverse proxy (nginx/caddy) with SSL
5. Set up monitoring and logging

### Environment Variables for Production

```env
APP_ENV=production
DEBUG=False
LOG_LEVEL=INFO
ALLOWED_ORIGINS=https://your-domain.com
```

## License

[Your License Here]

## Support

For issues and questions, please open an issue on GitHub.
