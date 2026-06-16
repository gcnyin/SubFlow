"""Tests for subtitle translation."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import Response

from subflow.models import SubtitleItem
from subflow.translate import (
    OpenAITranslator,
    _build_messages,
    _parse_response,
    create_translator,
)


def _make_items(count: int = 3) -> list[SubtitleItem]:
    return [
        SubtitleItem(
            index=i + 1, start=i * 2.0, end=i * 2.0 + 1.5,
            text=f"原文句子 {i + 1}", words=[],
        )
        for i in range(count)
    ]


class TestBuildMessages:
    """Tests for _build_messages prompt construction."""

    def test_basic_structure(self) -> None:
        """Messages should include system and user roles."""
        items = _make_items(2)
        messages = _build_messages(items, "zh", "en")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_contains_source_and_target_lang(self) -> None:
        """System prompt should mention source and target languages."""
        items = _make_items(1)
        messages = _build_messages(items, "zh", "ja")
        assert "zh" in messages[0]["content"]
        assert "ja" in messages[0]["content"]

    def test_contains_sentence_count(self) -> None:
        """System prompt should include the expected sentence count."""
        items = _make_items(5)
        messages = _build_messages(items, "en", "fr")
        assert "5" in messages[0]["content"]

    def test_contains_input_json(self) -> None:
        """System prompt should embed the input JSON."""
        items = _make_items(1)
        messages = _build_messages(items, "zh", "en")
        assert "原文句子 1" in messages[0]["content"]
        assert '"i":1' in messages[0]["content"]

    def test_empty_items(self) -> None:
        """Empty items should still produce valid messages."""
        messages = _build_messages([], "zh", "en")
        assert len(messages) == 2
        assert '"count":0' in messages[0]["content"] or "0 sentences" in messages[0]["content"]


class TestParseResponse:
    """Tests for _parse_response LLM output parsing."""

    def test_valid_json(self) -> None:
        """Valid JSON array should be parsed directly."""
        response = '[{"i":1,"t":"Hello"},{"i":2,"t":"World"}]'
        result = _parse_response(response, 2)
        assert len(result) == 2
        assert result[0]["t"] == "Hello"
        assert result[1]["t"] == "World"

    def test_json_with_surrounding_text(self) -> None:
        """JSON embedded in text should be extracted."""
        response = 'Here is the translation:\n```json\n[{"i":1,"t":"Hello"}]\n```'
        result = _parse_response(response, 1)
        assert len(result) == 1
        assert result[0]["t"] == "Hello"

    def test_invalid_json_raises(self) -> None:
        """Completely invalid text should raise ValueError."""
        response = "I'm sorry, I cannot translate that."
        with pytest.raises(ValueError, match="无法解析"):
            _parse_response(response, 1)

    def test_malformed_json_array(self) -> None:
        """Malformed JSON should raise ValueError."""
        response = "[{'i':1,'t':'Hello'}]"
        with pytest.raises(ValueError, match="无法解析"):
            _parse_response(response, 1)


class TestOpenAITranslator:
    """Tests for OpenAITranslator integration."""

    def test_translate_empty(self) -> None:
        """Empty items should return empty list without API call."""
        translator = OpenAITranslator(api_key="sk-test")
        result = translator.translate([], "zh", "en")
        assert result == []

    def _mock_response(self, content: str, status: int = 200) -> MagicMock:
        """Create a mock httpx Response."""
        mock = MagicMock(spec=Response)
        mock.status_code = status
        mock.json.return_value = {
            "choices": [{"message": {"content": content}}],
        }
        mock.raise_for_status = MagicMock()
        if status >= 400:
            from httpx import HTTPStatusError
            mock.raise_for_status.side_effect = HTTPStatusError(
                "error", request=MagicMock(), response=mock
            )
        return mock

    def test_successful_translation(self) -> None:
        """Successful API call should return translated items."""
        items = _make_items(2)
        response_text = '[{"i":1,"t":"Sentence 1"},{"i":2,"t":"Sentence 2"}]'

        translator = OpenAITranslator(api_key="sk-test")
        with patch.object(translator, "_call_api", return_value=response_text):
            result = translator.translate(items, "zh", "en")

        assert len(result) == 2
        assert result[0].text == "Sentence 1"
        assert result[1].text == "Sentence 2"
        # Time ranges preserved
        assert result[0].start == 0.0
        assert result[0].end == 1.5

    def test_missing_entry_fallback_to_source(self) -> None:
        """Missing translation entry should fall back to source text."""
        items = _make_items(3)
        # LLM only returns 2 entries, missing index 2
        response_text = '[{"i":1,"t":"One"},{"i":3,"t":"Three"}]'

        translator = OpenAITranslator(api_key="sk-test")
        with patch.object(translator, "_call_api", return_value=response_text):
            result = translator.translate(items, "zh", "en")

        assert len(result) == 3
        assert result[0].text == "One"
        assert result[1].text == "原文句子 2"  # Fallback to source
        assert result[2].text == "Three"

    def test_retry_on_connect_error(self) -> None:
        """Should retry on connection errors via the real retry logic."""
        items = _make_items(1)
        translator = OpenAITranslator(api_key="sk-test", max_retries=1)

        import httpx
        with patch("httpx.post") as mock_post:
            # First: connection refused, second: success
            fail_response = MagicMock()
            fail_response.status_code = 200  # Not 429, so no 429 sleep path
            fail_response.json.return_value = {
                "choices": [{"message": {"content": '[{"i":1,"t":"Success"}]'}}],
            }
            fail_response.raise_for_status = MagicMock()

            mock_post.side_effect = [
                httpx.ConnectError("connection refused"),
                fail_response,
            ]
            result = translator.translate(items, "zh", "en")
            assert result[0].text == "Success"
            assert mock_post.call_count == 2

    def test_create_translator_factory(self) -> None:
        """Factory should create translator from config."""
        from subflow.config import TranslatorConfig

        config = TranslatorConfig(
            base_url="https://custom.api/v1",
            api_key="sk-custom",
            model="custom-model",
            temperature=0.1,
        )
        translator = create_translator(config)
        assert isinstance(translator, OpenAITranslator)
        assert translator.base_url == "https://custom.api/v1"
        assert translator.api_key == "sk-custom"
        assert translator.model == "custom-model"
        assert translator.temperature == 0.1
