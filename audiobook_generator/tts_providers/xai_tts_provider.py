import io
import logging
import os

import requests

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.utils.utils import split_text, set_audio_tags, merge_audio_segments
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider

logger = logging.getLogger(__name__)

XAI_TTS_API_URL = "https://api.x.ai/v1/tts"
MAX_CHARS = 14000  # stay under the 15000 char limit


def get_xai_supported_voices():
    return ["eve", "ara", "rex", "sal", "leo"]


def get_xai_supported_output_formats():
    return ["mp3", "wav", "pcm", "mulaw", "alaw"]


def get_xai_supported_languages():
    return [
        "auto", "en", "zh", "ar", "fr", "de", "hi", "id", "it",
        "ja", "ko", "pt", "pt-BR", "ru", "es", "es-419", "tr", "vi",
    ]


class XAITTSProvider(BaseTTSProvider):
    def __init__(self, config: GeneralConfig):
        config.voice_name = config.voice_name or "eve"
        config.output_format = config.output_format or "mp3"
        config.language = config.language or "en"
        super().__init__(config)
        self.api_key = os.environ["XAI_API_KEY"]

    def __str__(self):
        return super().__str__()

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        text_chunks = split_text(text, MAX_CHARS, self.config.language)
        audio_segments = []
        chunk_ids = []

        for i, chunk in enumerate(text_chunks, 1):
            chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(text_chunks)}"
            logger.info(f"Processing {chunk_id}, length={len(chunk)}")
            logger.debug(f"Processing {chunk_id}, length={len(chunk)}, text=[{chunk}]")

            output_format = {"codec": self.config.output_format}
            if self.config.xai_sample_rate:
                output_format["sample_rate"] = self.config.xai_sample_rate
            if self.config.xai_bit_rate and self.config.output_format == "mp3":
                output_format["bit_rate"] = self.config.xai_bit_rate

            response = requests.post(
                XAI_TTS_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "text": chunk,
                    "voice_id": self.config.voice_name,
                    "language": self.config.language,
                    "output_format": output_format,
                },
                timeout=60,
            )
            response.raise_for_status()

            logger.debug(
                f"Remote server response: status_code={response.status_code}, "
                f"size={len(response.content)} bytes"
            )
            audio_segments.append(io.BytesIO(response.content))
            chunk_ids.append(chunk_id)

        merge_audio_segments(
            audio_segments, output_file, self.config.output_format,
            chunk_ids, self.config.use_pydub_merge
        )
        set_audio_tags(output_file, audio_tags)

    def get_break_string(self):
        return "   "

    def get_output_file_extension(self):
        return self.config.output_format

    def validate_config(self):
        if "XAI_API_KEY" not in os.environ:
            raise ValueError("xAI: XAI_API_KEY environment variable not set")
        if self.config.output_format not in get_xai_supported_output_formats():
            raise ValueError(f"xAI: Unsupported output format: {self.config.output_format}")
        if self.config.voice_name.lower() not in get_xai_supported_voices():
            raise ValueError(f"xAI: Unsupported voice: {self.config.voice_name}")

    def estimate_cost(self, total_chars):
        # xAI TTS pricing not yet published
        return 0.0
