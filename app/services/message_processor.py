from typing import Optional
from sqlalchemy.orm import Session
import structlog

from app.models.database import MessageType, MessageDirection
from app.models.crud import UserCRUD, ConversationCRUD, MessageCRUD
from app.services.openai_service import openai_service
from app.services.twilio_service import twilio_service
from app.services.media_service import media_service
from config.settings import settings

logger = structlog.get_logger()


class MessageProcessor:
    """Main message processing orchestrator"""

    def __init__(self, db: Session):
        self.db = db
        self.whitelisted_numbers = settings.get_whitelisted_numbers()

    async def process_incoming_message(
        self,
        from_number: str,
        message_body: str,
        message_type: MessageType,
        media_url: Optional[str] = None,
        media_content_type: Optional[str] = None,
        twilio_message_sid: Optional[str] = None,
        whatsapp_name: Optional[str] = None
    ) -> bool:
        """
        Process incoming WhatsApp message

        Args:
            from_number: Sender's phone number
            message_body: Message text
            message_type: Type of message
            media_url: URL of media file if any
            media_content_type: Content type of media
            twilio_message_sid: Twilio message ID
            whatsapp_name: Sender's WhatsApp name

        Returns:
            bool: True if processed successfully
        """
        try:
            # Get or create user
            user = UserCRUD.get_or_create_user(
                self.db,
                from_number,
                whatsapp_name,
                self.whitelisted_numbers
            )

            logger.info(
                "processing_message",
                user_id=user.id,
                phone=from_number,
                message_type=message_type,
                whitelisted=user.is_whitelisted
            )

            # Check if user is whitelisted
            if not user.is_whitelisted:
                logger.warning("user_not_whitelisted", phone=from_number)
                await self._send_not_whitelisted_message(from_number)
                return False

            # Get or create active conversation
            conversation = ConversationCRUD.get_or_create_conversation(self.db, user.id)

            # Create incoming message record
            incoming_message = MessageCRUD.create_message(
                self.db,
                user_id=user.id,
                conversation_id=conversation.id,
                direction=MessageDirection.INCOMING,
                message_type=message_type,
                content=message_body,
                media_url=media_url,
                media_content_type=media_content_type,
                twilio_message_sid=twilio_message_sid
            )

            # Process based on message type
            if message_type == MessageType.TEXT:
                response_text = await self._process_text_message(
                    message_body,
                    conversation.id,
                    incoming_message.id
                )

            elif message_type == MessageType.IMAGE:
                response_text = await self._process_image_message(
                    media_url,
                    message_body,
                    incoming_message.id
                )

            elif message_type == MessageType.AUDIO:
                response_text = await self._process_audio_message(
                    media_url,
                    incoming_message.id
                )

            elif message_type == MessageType.DOCUMENT:
                response_text = await self._process_document_message(
                    media_url,
                    media_content_type,
                    message_body,
                    incoming_message.id
                )

            else:
                response_text = "Sorry, I cannot process this type of message yet."

            # Send response
            await self._send_response(
                from_number,
                response_text,
                user.id,
                conversation.id
            )

            return True

        except Exception as e:
            logger.error("message_processing_error", error=str(e), phone=from_number)
            await self._send_error_message(from_number)
            return False

    async def _process_text_message(
        self,
        message_text: str,
        conversation_id: int,
        message_id: int
    ) -> str:
        """Process text message and generate AI response"""
        try:
            # Get conversation history
            history_messages = MessageCRUD.get_conversation_history(
                self.db,
                conversation_id,
                limit=settings.max_conversation_history
            )

            # Build context from history (reverse to get chronological order)
            conversation_context = []
            for msg in reversed(history_messages):
                if msg.content:
                    role = "user" if msg.direction == MessageDirection.INCOMING else "assistant"
                    conversation_context.append({
                        "role": role,
                        "content": msg.content
                    })

            # Generate AI response
            response_text, prompt_tokens, completion_tokens = await openai_service.generate_response(
                message_text,
                conversation_context[:-1] if conversation_context else []  # Exclude current message
            )

            # Update message with AI response
            MessageCRUD.mark_as_processed(
                self.db,
                message_id,
                ai_response=response_text,
                ai_model=settings.openai_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )

            return response_text

        except Exception as e:
            logger.error("text_processing_error", error=str(e))
            MessageCRUD.mark_as_processed(
                self.db,
                message_id,
                error_message=str(e)
            )
            raise

    async def _process_image_message(
        self,
        media_url: str,
        caption: str,
        message_id: int
    ) -> str:
        """Process image message with vision AI"""
        try:
            # Download image with Twilio authentication
            auth = (settings.twilio_account_sid, settings.twilio_auth_token)
            image_path = await media_service.download_media(media_url, auth)

            if not image_path:
                return "Sorry, I couldn't download the image."

            # Analyze image
            prompt = f"Describe this image. {caption}" if caption else "Describe this image in detail."
            analysis, prompt_tokens, completion_tokens = await openai_service.analyze_image(
                media_url,  # OpenAI can fetch from URL
                prompt
            )

            # Clean up downloaded file
            media_service.cleanup_file(image_path)

            # Update message
            MessageCRUD.mark_as_processed(
                self.db,
                message_id,
                ai_response=analysis,
                ai_model=settings.vision_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )

            return analysis

        except Exception as e:
            logger.error("image_processing_error", error=str(e))
            MessageCRUD.mark_as_processed(
                self.db,
                message_id,
                error_message=str(e)
            )
            return "Sorry, I encountered an error analyzing the image."

    async def _process_audio_message(
        self,
        media_url: str,
        message_id: int
    ) -> str:
        """Process audio message with transcription"""
        try:
            # Download audio with Twilio authentication
            auth = (settings.twilio_account_sid, settings.twilio_auth_token)
            audio_path = await media_service.download_media(media_url, auth)

            if not audio_path:
                return "Sorry, I couldn't download the audio."

            # Transcribe audio
            transcription = await openai_service.transcribe_audio(audio_path)

            # Clean up downloaded file
            media_service.cleanup_file(audio_path)

            # Update message with transcription
            MessageCRUD.update_message(self.db, message_id, content=transcription)

            # Generate response based on transcribed text
            response_text = await self._process_text_message(
                transcription,
                MessageCRUD.update_message(self.db, message_id).conversation_id,
                message_id
            )

            return f"I heard: '{transcription}'\n\n{response_text}"

        except Exception as e:
            logger.error("audio_processing_error", error=str(e))
            MessageCRUD.mark_as_processed(
                self.db,
                message_id,
                error_message=str(e)
            )
            return "Sorry, I encountered an error processing the audio."

    async def _process_document_message(
        self,
        media_url: str,
        content_type: str,
        caption: str,
        message_id: int
    ) -> str:
        """Process document message"""
        try:
            # Download document with Twilio authentication
            auth = (settings.twilio_account_sid, settings.twilio_auth_token)
            doc_path = await media_service.download_media(media_url, auth)

            if not doc_path:
                return "Sorry, I couldn't download the document."

            # Extract text from PDF
            if content_type == 'application/pdf':
                extracted_text = await media_service.extract_text_from_pdf(doc_path)
                media_service.cleanup_file(doc_path)

                if not extracted_text:
                    return "Sorry, I couldn't extract text from the PDF."

                # Generate summary or response
                prompt = f"Summarize this document: {extracted_text[:3000]}"  # Limit text
                response_text, prompt_tokens, completion_tokens = await openai_service.generate_response(
                    prompt,
                    []
                )

                MessageCRUD.mark_as_processed(
                    self.db,
                    message_id,
                    ai_response=response_text,
                    ai_model=settings.openai_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens
                )

                return response_text
            else:
                media_service.cleanup_file(doc_path)
                return "I can only process PDF documents at the moment."

        except Exception as e:
            logger.error("document_processing_error", error=str(e))
            MessageCRUD.mark_as_processed(
                self.db,
                message_id,
                error_message=str(e)
            )
            return "Sorry, I encountered an error processing the document."

    async def _send_response(
        self,
        to_number: str,
        message: str,
        user_id: int,
        conversation_id: int
    ):
        """Send response message via Twilio"""
        # Send via Twilio
        message_sid = await twilio_service.send_message(to_number, message)

        # Record outgoing message
        if message_sid:
            MessageCRUD.create_message(
                self.db,
                user_id=user_id,
                conversation_id=conversation_id,
                direction=MessageDirection.OUTGOING,
                message_type=MessageType.TEXT,
                content=message,
                twilio_message_sid=message_sid
            )

    async def _send_not_whitelisted_message(self, to_number: str):
        """Send message to non-whitelisted user"""
        message = (
            "Sorry, you are not authorized to use this bot. "
            "Please contact the administrator for access."
        )
        await twilio_service.send_message(to_number, message)

    async def _send_error_message(self, to_number: str):
        """Send error message to user"""
        message = (
            "Sorry, I encountered an error processing your message. "
            "Please try again later."
        )
        await twilio_service.send_message(to_number, message)
