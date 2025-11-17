from typing import List, Dict, Optional, Tuple
from openai import OpenAI
import structlog

from config.settings import settings

logger = structlog.get_logger()


class OpenAIService:
    """Service for OpenAI API interactions"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.max_tokens = settings.openai_max_tokens
        self.temperature = settings.openai_temperature

    def build_conversation_context(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Build conversation context from message history

        Args:
            messages: List of messages with 'role' and 'content'

        Returns:
            List of formatted messages for OpenAI API
        """
        # System message with bot instructions
        context = [
            {
                "role": "system",
                "content": (
                    "Sen WhatsApp üzerinden erişilebilen yardımcı bir yapay zeka asistanısın. "
                    "Türkçe konuşan kullanıcılara hizmet veriyorsun. "
                    "Samimi, dostça ve yardımsever yanıtlar ver. "
                    "Mesajlarını kısa ve sohbet havasında tut, WhatsApp sohbetine uygun şekilde yaz. "
                    "Konuşmayı daha ilgi çekici hale getirmek için uygun yerlerde emoji kullan. "
                    "Kullanıcıların sorularını anla ve net, faydalı cevaplar sun. "
                    "Türk kültürüne ve Türkiye'deki güncel olaylara aşina ol."
                )
            }
        ]

        # Add conversation history
        context.extend(messages)

        return context

    async def generate_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]] = None
    ) -> Tuple[str, int, int]:
        """
        Generate AI response for user message

        Args:
            user_message: User's message text
            conversation_history: Previous messages in conversation

        Returns:
            Tuple of (response_text, prompt_tokens, completion_tokens)
        """
        try:
            # Build messages
            messages = conversation_history or []
            messages.append({"role": "user", "content": user_message})

            # Build context
            context = self.build_conversation_context(messages)

            # Call OpenAI API
            # Use max_completion_tokens for newer models (gpt-4-turbo and later)
            completion_params = {
                "model": self.model,
                "messages": context,
                "temperature": self.temperature
            }

            # Newer models use max_completion_tokens instead of max_tokens
            if "gpt-4-turbo" in self.model or "gpt-4o" in self.model or "o1" in self.model or "gpt-5" in self.model:
                completion_params["max_completion_tokens"] = self.max_tokens
            else:
                completion_params["max_tokens"] = self.max_tokens

            response = self.client.chat.completions.create(**completion_params)

            # Extract response
            assistant_message = response.choices[0].message.content
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens

            logger.info(
                "openai_response_generated",
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )

            return assistant_message, prompt_tokens, completion_tokens

        except Exception as e:
            logger.error("openai_error", error=str(e))
            raise

    async def analyze_image(self, image_url: str, prompt: str = None) -> Tuple[str, int, int]:
        """
        Analyze image using OpenAI Vision API

        Args:
            image_url: URL of the image
            prompt: Optional custom prompt for analysis

        Returns:
            Tuple of (analysis_text, prompt_tokens, completion_tokens)
        """
        try:
            default_prompt = "Describe this image in detail. What do you see?"
            analysis_prompt = prompt or default_prompt

            # Build vision API params
            vision_params = {
                "model": settings.vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": analysis_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url}
                            }
                        ]
                    }
                ]
            }

            # Newer models use max_completion_tokens instead of max_tokens
            if "gpt-4-turbo" in settings.vision_model or "gpt-4o" in settings.vision_model or "o1" in settings.vision_model or "gpt-5" in settings.vision_model:
                vision_params["max_completion_tokens"] = settings.vision_max_tokens
            else:
                vision_params["max_tokens"] = settings.vision_max_tokens

            response = self.client.chat.completions.create(**vision_params)

            analysis = response.choices[0].message.content
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens

            logger.info(
                "image_analysis_completed",
                model=settings.vision_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )

            return analysis, prompt_tokens, completion_tokens

        except Exception as e:
            logger.error("image_analysis_error", error=str(e))
            raise

    async def transcribe_audio(self, audio_file_path: str) -> str:
        """
        Transcribe audio using Whisper API

        Args:
            audio_file_path: Path to audio file

        Returns:
            Transcribed text
        """
        try:
            with open(audio_file_path, 'rb') as audio_file:
                response = self.client.audio.transcriptions.create(
                    model=settings.whisper_model,
                    file=audio_file
                )

            transcription = response.text

            logger.info(
                "audio_transcription_completed",
                model=settings.whisper_model,
                text_length=len(transcription)
            )

            return transcription

        except Exception as e:
            logger.error("audio_transcription_error", error=str(e))
            raise


# Global instance
openai_service = OpenAIService()
