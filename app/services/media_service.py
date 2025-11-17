import os
import httpx
from typing import Optional, Tuple
from pathlib import Path
import structlog
from PyPDF2 import PdfReader

from config.settings import settings

logger = structlog.get_logger()


class MediaService:
    """Service for handling media files (images, audio, documents)"""

    def __init__(self):
        self.temp_dir = Path(settings.temp_media_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = settings.media_max_size_mb * 1024 * 1024
        self.timeout = settings.media_download_timeout

    async def download_media(
        self,
        media_url: str,
        auth: Optional[Tuple[str, str]] = None
    ) -> Optional[str]:
        """
        Download media file from URL

        Args:
            media_url: URL of the media file
            auth: Optional tuple of (username, password) for authentication

        Returns:
            Path to downloaded file or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Make request with optional authentication
                if auth:
                    response = await client.get(media_url, auth=auth)
                else:
                    response = await client.get(media_url)

                response.raise_for_status()

                # Check file size
                content_length = int(response.headers.get('content-length', 0))
                if content_length > self.max_size_bytes:
                    logger.warning(
                        "media_too_large",
                        size_mb=content_length / (1024 * 1024),
                        max_mb=settings.media_max_size_mb
                    )
                    return None

                # Generate filename
                content_type = response.headers.get('content-type', 'application/octet-stream')
                extension = self._get_extension_from_content_type(content_type)
                filename = f"{os.urandom(16).hex()}{extension}"
                file_path = self.temp_dir / filename

                # Save file
                with open(file_path, 'wb') as f:
                    f.write(response.content)

                logger.info(
                    "media_downloaded",
                    filename=filename,
                    size_bytes=len(response.content),
                    content_type=content_type
                )

                return str(file_path)

        except Exception as e:
            logger.error("media_download_error", error=str(e), url=media_url)
            return None

    def _get_extension_from_content_type(self, content_type: str) -> str:
        """Get file extension from content type"""
        extensions = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'audio/ogg': '.ogg',
            'audio/mpeg': '.mp3',
            'audio/mp4': '.mp4',
            'audio/amr': '.amr',
            'video/mp4': '.mp4',
            'application/pdf': '.pdf',
            'application/msword': '.doc',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        }
        return extensions.get(content_type, '.bin')

    async def extract_text_from_pdf(self, pdf_path: str) -> Optional[str]:
        """
        Extract text from PDF file

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text or None if failed
        """
        try:
            reader = PdfReader(pdf_path)
            text_parts = []

            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            extracted_text = "\n".join(text_parts)

            logger.info(
                "pdf_text_extracted",
                pages=len(reader.pages),
                text_length=len(extracted_text)
            )

            return extracted_text

        except Exception as e:
            logger.error("pdf_extraction_error", error=str(e), path=pdf_path)
            return None

    def cleanup_file(self, file_path: str):
        """
        Delete temporary file

        Args:
            file_path: Path to file to delete
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info("media_file_cleaned", path=file_path)
        except Exception as e:
            logger.error("file_cleanup_error", error=str(e), path=file_path)

    def cleanup_old_files(self, max_age_hours: int = 24):
        """
        Clean up old temporary files

        Args:
            max_age_hours: Delete files older than this many hours
        """
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            deleted_count = 0

            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        deleted_count += 1

            if deleted_count > 0:
                logger.info("old_media_cleaned", count=deleted_count)

        except Exception as e:
            logger.error("cleanup_error", error=str(e))


# Global instance
media_service = MediaService()
