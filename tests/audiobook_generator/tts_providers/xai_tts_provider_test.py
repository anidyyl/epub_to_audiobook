import unittest
from unittest.mock import patch

from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider
from audiobook_generator.tts_providers.xai_tts_provider import XAITTSProvider
from tests.test_utils import get_xai_config


class TestXAITtsProvider(unittest.TestCase):

    def test_missing_env_var_keys(self):
        config = get_xai_config()
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                get_tts_provider(config)

    @patch.dict('os.environ', {'XAI_API_KEY': 'fake_key'})
    def test_estimate_cost(self):
        config = get_xai_config()
        provider = get_tts_provider(config)
        self.assertIsInstance(provider, XAITTSProvider)
        self.assertEqual(provider.estimate_cost(1000000), 0.0)

    @patch.dict('os.environ', {'XAI_API_KEY': 'fake_key'})
    def test_default_args(self):
        config = get_xai_config()
        config.voice_name = None
        config.output_format = None
        config.language = None
        provider = get_tts_provider(config)
        self.assertIsInstance(provider, XAITTSProvider)
        self.assertEqual(provider.config.voice_name, "eve")
        self.assertEqual(provider.config.output_format, "mp3")
        self.assertEqual(provider.config.language, "en")

    @patch.dict('os.environ', {'XAI_API_KEY': 'fake_key'})
    def test_invalid_output_format(self):
        config = get_xai_config()
        config.output_format = "ogg"
        with self.assertRaises(ValueError):
            get_tts_provider(config)

    @patch.dict('os.environ', {'XAI_API_KEY': 'fake_key'})
    def test_invalid_voice(self):
        config = get_xai_config()
        config.voice_name = "invalid_voice"
        with self.assertRaises(ValueError):
            get_tts_provider(config)
