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


DEFAULT_BATCH_SIZE = 40


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
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.extra_params = extra_params or {}
        self.max_retries = max_retries
        self.batch_size = batch_size

    def _call_api(self, messages: list[dict[str, str]], batch_label: str = "") -> str:
        """Call the chat completions API with retry logic.

        Args:
            messages: Chat messages.
            batch_label: Optional label for log messages (e.g. "[1/15]").

        Returns:
            Raw response text from the LLM.

        Raises:
            httpx.HTTPError: On network/API failure after retries.
        """
        last_error: Exception | None = None
        label = f"{batch_label} " if batch_label else ""

        for attempt in range(self.max_retries + 1):
            try:
                t0 = time.time()
                logger.info("%s调用 API (%s)...", label, self.model)
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
                    logger.warning("%s频率限制, 等待 %ds...", label, wait)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                body = resp.json()
                content: str = body["choices"][0]["message"]["content"]
                elapsed = time.time() - t0
                logger.info("%sAPI 响应 (%.1fs)", label, elapsed)
                return content

            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError) as e:
                last_error = e
                logger.warning("%sAPI 调用失败 (尝试 %d/%d): %s", label, attempt + 1, self.max_retries + 1, e)
                if attempt < self.max_retries:
                    wait = 2**attempt
                    time.sleep(wait)

        raise last_error if last_error is not None else RuntimeError(
            "Translation API call failed after retries")

    def translate(
        self,
        items: list[SubtitleItem],
        source_lang: str,
        target_lang: str,
    ) -> list[SubtitleItem]:
        """Translate subtitle items via OpenAI-compatible API.

        Splits items into batches for better progress visibility and reliability.

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

        total = len(items)
        batch_size = self.batch_size
        total_batches = (total + batch_size - 1) // batch_size

        logger.info("开始翻译: %s -> %s, 共 %d 句, 分 %d 批 (每批 <=%d 句)",
                     source_lang, target_lang, total, total_batches, batch_size)

        all_results: dict[int, str] = {}  # index → translated text
        overall_t0 = time.time()

        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, total)
            batch_items = items[start:end]
            batch_label = f"[{batch_idx + 1}/{total_batches}]"

            logger.info("%s 第 %d 批: 句 %d-%d (%d 句)",
                         batch_label, batch_idx + 1, batch_items[0].index, batch_items[-1].index, len(batch_items))

            # Build messages for this batch
            t0 = time.time()
            messages = _build_messages(batch_items, source_lang, target_lang)
            build_time = time.time() - t0
            logger.info("%s 构建提示词 (%.1fs, %.1fKB)",
                         batch_label, build_time, len(messages[0]["content"]) / 1024)

            # Call API
            response_text = self._call_api(messages, batch_label)

            # Parse response
            t0 = time.time()
            data = _parse_response(response_text, len(batch_items))
            parse_time = time.time() - t0
            logger.info("%s 解析响应 (%.1fs), 得到 %d 条", batch_label, parse_time, len(data))

            # Merge results
            for entry in data:
                idx = entry.get("i")
                text = entry.get("t", "")
                if isinstance(idx, int) and isinstance(text, str) and text.strip():
                    all_results[idx] = text.strip()

        # Build final result, matching by index
        missing_count = 0
        result: list[SubtitleItem] = []
        for item in items:
            new_text = all_results.get(item.index)
            if new_text is None:
                logger.warning("索引 %d 的翻译缺失, 保留原文", item.index)
                new_text = item.text
                missing_count += 1

            result.append(
                SubtitleItem(
                    index=item.index,
                    start=item.start,
                    end=item.end,
                    text=new_text,
                    words=[],
                )
            )

        overall_elapsed = time.time() - overall_t0
        logger.info("翻译完成: %d/%d 句 (%.1fs), 缺失 %d 句",
                     total - missing_count, total, overall_elapsed, missing_count)

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
