"""Subtitle translation — abstract interface and OpenAI-compatible implementation."""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from subflow.logging import get_logger
from subflow.models import SubtitleItem

logger = get_logger(__name__)

# ── Prompt template ──

_SYSTEM_PROMPT = """\
You are a professional subtitle translator.

Translate the following sentences from {source_lang} to {target_lang}.

Rules:
- Translate each sentence naturally, as a native {target_lang} speaker would say it.
- Maintain a strict 1:1 mapping — do NOT merge or split sentences.
  Output exactly {count} entries.
- Preserve tone, intent, and conversational flow.
- Do NOT add explanations, notes, or extra text.
- Output ONLY valid JSON in this exact format.

Examples of natural translation at sentence level:

zh→en:
Input:  [{{"i":1,"t":"今天天气真好。"}},{{"i":2,"t":"我们去公园散步吧。"}}]
Output: [{{"i":1,"t":"The weather is really nice today."}},
         {{"i":2,"t":"Let's go for a walk in the park."}}]

en→zh:
Input:  [{{"i":1,"t":"I can't believe you did that."}},{{"i":2,"t":"That was awesome."}}]
Output: [{{"i":1,"t":"真不敢相信你做到了。"}},{{"i":2,"t":"太厉害了。"}}]

ja→en:
Input:  [{{"i":1,"t":"すみません、駅はどこですか？"}},{{"i":2,"t":"ありがとうございます。"}}]
Output: [{{"i":1,"t":"Excuse me, where is the station?"}},{{"i":2,"t":"Thank you very much."}}]

Now translate the following {count} sentences from {source_lang} to {target_lang}:

Input:
{json_input}"""

_USER_PROMPT = "Translate these sentences."


def _build_messages(
    items: list[SubtitleItem],
    source_lang: str,
    target_lang: str,
) -> list[dict[str, str]]:
    """Build the chat messages for the translation request."""
    input_data = [{"i": item.index, "t": item.text} for item in items]
    json_input = json.dumps(input_data, ensure_ascii=False)

    system = _SYSTEM_PROMPT.format(
        source_lang=source_lang,
        target_lang=target_lang,
        count=len(items),
        json_input=json_input,
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _USER_PROMPT},
    ]


def _parse_response(response_text: str, expected_count: int) -> list[dict[str, Any]]:
    """Parse LLM response into list of {i, t} dicts.

    Attempts:
    1. Direct JSON parse
    2. Extract JSON array from surrounding text
    3. Fallback: return empty list

    Args:
        response_text: Raw LLM response.
        expected_count: Expected number of entries.

    Returns:
        List of dicts with 'i' and 't' keys.

    Raises:
        ValueError: If parsing fails completely.
    """
    # Try direct parse
    try:
        data = json.loads(response_text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try extracting JSON array from surrounding text
    match = re.search(r"\[.*\]", response_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法解析 LLM 响应为 JSON\n原始响应:\n{response_text[:500]}")


# ── Translator interface ──


class Translator(ABC):
    """Abstract interface for subtitle translation engines."""

    @abstractmethod
    def translate(
        self,
        items: list[SubtitleItem],
        source_lang: str,
        target_lang: str,
    ) -> list[SubtitleItem]:
        """Translate subtitle items. Returns same count, same time ranges, translated text."""
        ...


class OpenAITranslator(Translator):
    """Translator backed by any OpenAI-compatible chat completions API."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        extra_params: dict[str, Any] | None = None,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.extra_params = extra_params or {}
        self.max_retries = max_retries

    def _call_api(self, messages: list[dict[str, str]]) -> str:
        """Call the chat completions API with retry logic.

        Args:
            messages: Chat messages.

        Returns:
            Raw response text from the LLM.

        Raises:
            httpx.HTTPError: On network/API failure after retries.
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": self.temperature,
                        **self.extra_params,
                    },
                    timeout=120.0,
                )

                if resp.status_code == 429:
                    wait = 2**attempt
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                body = resp.json()
                content: str = body["choices"][0]["message"]["content"]
                return content

            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError) as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(2**attempt)

        raise last_error if last_error is not None else RuntimeError(
            "Translation API call failed after retries")

    def translate(
        self,
        items: list[SubtitleItem],
        source_lang: str,
        target_lang: str,
    ) -> list[SubtitleItem]:
        """Translate subtitle items via OpenAI-compatible API.

        Args:
            items: Source subtitle items with time ranges.
            source_lang: Source language code (e.g. 'zh').
            target_lang: Target language code (e.g. 'en').

        Returns:
            New SubtitleItem list with translated text, preserving time ranges.

        Raises:
            ValueError: If the LLM returns unparseable output or wrong count.
        """
        if not items:
            return []

        messages = _build_messages(items, source_lang, target_lang)
        response_text = self._call_api(messages)
        data = _parse_response(response_text, len(items))

        # Build result, matching by index
        translated_map: dict[int, str] = {}
        for entry in data:
            idx = entry.get("i")
            text = entry.get("t", "")
            if isinstance(idx, int) and isinstance(text, str) and text.strip():
                translated_map[idx] = text.strip()

        result: list[SubtitleItem] = []
        for item in items:
            new_text = translated_map.get(item.index)
            if new_text is None:
                logger.warning("索引 %d 的翻译缺失，保留原文", item.index)
                new_text = item.text

            result.append(
                SubtitleItem(
                    index=item.index,
                    start=item.start,
                    end=item.end,
                    text=new_text,
                    words=[],  # No word-level timestamps for translated text
                )
            )

        return result


def create_translator(config: Any) -> OpenAITranslator:
    """Factory to create the default translator from config."""
    return OpenAITranslator(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        temperature=config.temperature,
        extra_params=dict(config.extra_params),
    )
