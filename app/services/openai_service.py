import asyncio
from typing import Dict, List, Optional, Tuple

import structlog
from openai import BadRequestError, OpenAI

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
        conversation_history: Optional[List[Dict[str, str]]] = None,
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
            messages = list(conversation_history or [])
            messages.append({"role": "user", "content": user_message})

            # Build context
            context = self.build_conversation_context(messages)

            response = await self._create_completion(context)

            # Extract response
            assistant_message = self._extract_text(response)
            prompt_tokens, completion_tokens = self._extract_usage_tokens(response)

            # Ensure we have a valid response
            if not assistant_message or not assistant_message.strip():
                logger.error(
                    "openai_empty_response",
                    model=self.model,
                    content_value=repr(assistant_message),
                )
                assistant_message = "Üzgünüm, şu anda bir yanıt oluşturamadım. Lütfen tekrar deneyin."

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

    async def analyze_image(self, image_url: str, prompt: Optional[str] = None) -> Tuple[str, int, int]:
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

            response = await self._create_vision_completion(image_url, analysis_prompt)

            analysis = self._extract_text(response)
            prompt_tokens, completion_tokens = self._extract_usage_tokens(response)

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
            def _transcribe() -> str:
                with open(audio_file_path, 'rb') as audio_file:
                    response = self.client.audio.transcriptions.create(
                        model=settings.whisper_model,
                        file=audio_file
                    )
                return response.text

            transcription = await asyncio.to_thread(_transcribe)

            logger.info(
                "audio_transcription_completed",
                model=settings.whisper_model,
                text_length=len(transcription)
            )

            return transcription

        except Exception as e:
            logger.error("audio_transcription_error", error=str(e))
            raise

    async def _create_completion(self, context: List[Dict[str, str]]):
        """Route completion creation to the correct API for the active model."""
        if self._uses_responses_api(self.model):
            return await self._call_responses_api(context)
        return await self._call_chat_api(context)

    async def _create_vision_completion(self, image_url: str, prompt: str):
        """Create a multimodal completion for image analysis."""
        if self._uses_responses_api(settings.vision_model):
            response_input = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ],
                }
            ]

            params = {
                "model": settings.vision_model,
                "input": response_input,
                "max_output_tokens": settings.vision_max_tokens,
            }

            if self._supports_temperature(settings.vision_model):
                params["temperature"] = self.temperature

            return await self._call_responses_api([], params_override=params)

        # Fallback to legacy chat completion vision call
        vision_params = {
            "model": settings.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }

        token_field = self._chat_token_field(settings.vision_model)
        vision_params[token_field] = settings.vision_max_tokens

        return await self._call_chat_api([], params_override=vision_params)

    async def _call_chat_api(
        self,
        context: List[Dict[str, str]],
        params_override: Optional[Dict] = None,
    ):
        """Execute a chat.completions.create call in a worker thread."""
        completion_params = params_override or {
            "model": self.model,
            "messages": context,
        }

        if params_override is None:
            if self._supports_temperature(self.model):
                completion_params["temperature"] = self.temperature

            token_field = self._chat_token_field(self.model)
            completion_params[token_field] = self.max_tokens

        try:
            return await asyncio.to_thread(self.client.chat.completions.create, **completion_params)
        except (TypeError, BadRequestError) as e:
            error_msg = str(e)
            if "max_completion_tokens" in error_msg:
                logger.warning("max_completion_tokens not supported by SDK/API, retrying with max_tokens")
                completion_params.pop("max_completion_tokens", None)
                completion_params["max_tokens"] = completion_params.get("max_tokens", self.max_tokens)
                return await asyncio.to_thread(self.client.chat.completions.create, **completion_params)
            if "max_tokens" in error_msg:
                logger.warning("max_tokens not supported by API, retrying with max_completion_tokens")
                completion_params.pop("max_tokens", None)
                completion_params["max_completion_tokens"] = completion_params.get("max_completion_tokens", self.max_tokens)
                return await asyncio.to_thread(self.client.chat.completions.create, **completion_params)
            raise

    async def _call_responses_api(
        self,
        context: List[Dict[str, str]],
        params_override: Optional[Dict] = None,
    ):
        """Execute a responses.create call for models that require it."""
        params = params_override or {
            "model": self.model,
            "input": self._convert_context_to_responses_input(context),
            "max_output_tokens": self.max_tokens,
        }

        if params_override is None and self._supports_temperature(self.model):
            params["temperature"] = self.temperature

        try:
            return await asyncio.to_thread(self.client.responses.create, **params)
        except (TypeError, BadRequestError) as e:
            error_msg = str(e)
            if "max_output_tokens" in error_msg:
                logger.warning("max_output_tokens not supported; retrying without token cap")
                params.pop("max_output_tokens", None)
                return await asyncio.to_thread(self.client.responses.create, **params)
            raise

    def _convert_context_to_responses_input(self, context: List[Dict[str, str]]):
        converted = []
        for message in context:
            text = message.get("content", "")
            converted.append(
                {
                    "role": message.get("role", "user"),
                    "content": [{"type": "text", "text": text}],
                }
            )
        return converted

    @staticmethod
    def _extract_usage_tokens(response) -> Tuple[int, int]:
        usage = getattr(response, "usage", None)
        if not usage:
            return 0, 0

        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)

        if prompt_tokens is None:
            prompt_tokens = getattr(usage, "input_tokens", 0)
        if completion_tokens is None:
            completion_tokens = getattr(usage, "output_tokens", 0)

        return prompt_tokens or 0, completion_tokens or 0

    @staticmethod
    def _extract_text(response) -> str:
        if hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content

        output_text = getattr(response, "output_text", None)
        if output_text:
            if isinstance(output_text, list):
                return "\n".join(t for t in output_text if t).strip()
            return str(output_text)

        output = getattr(response, "output", None) or []
        collected = []
        for item in output:
            contents = getattr(item, "content", None) or item.get("content", [])
            for content in contents:
                content_type = getattr(content, "type", None) or content.get("type")
                if content_type == "output_text":
                    text_value = getattr(content, "text", None) or content.get("text")
                    if text_value:
                        collected.append(text_value)
        return "\n".join(collected).strip()

    @staticmethod
    def _supports_temperature(model_name: str) -> bool:
        lowered = model_name.lower()
        unsupported_markers = ("o1", "gpt-5-nano")
        return not any(marker in lowered for marker in unsupported_markers)

    @staticmethod
    def _uses_responses_api(model_name: str) -> bool:
        lowered = model_name.lower()
        responses_markers = ("gpt-4.1", "gpt-4o", "o1", "gpt-5")
        return any(marker in lowered for marker in responses_markers)

    @staticmethod
    def _chat_token_field(model_name: str) -> str:
        lowered = model_name.lower()
        if any(marker in lowered for marker in ["gpt-4-turbo", "gpt-4o", "o1", "gpt-5"]):
            return "max_completion_tokens"
        return "max_tokens"


# Global instance
openai_service = OpenAIService()
