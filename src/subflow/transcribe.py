"""ASR transcription — abstract interface and faster-whisper implementation."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from subflow.models import WordTimestamp


class Transcriber(ABC):
    """Abstract interface for speech-to-text engines."""

    @abstractmethod
    def transcribe(self, audio_path: Path, **kwargs: Any) -> tuple[list[WordTimestamp], str]:
        """Transcribe an audio file and return word-level timestamps with detected language."""
        ...


class FasterWhisperTranscriber(Transcriber):
    """Transcriber backed by faster-whisper (CTranslate2)."""

    def __init__(
        self,
        model_size: str = "medium",
        device: str = "auto",
        compute_type: str = "auto",
        model_dir: str | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model_dir = model_dir
        self._model: Any = None

    def _load_model(self) -> Any:
        """Lazy-load the faster-whisper model."""
        if self._model is not None:
            return self._model

        from faster_whisper import WhisperModel  # type: ignore[import-untyped]

        print(f"📥 下载模型 {self.model_size} 中... (首次运行需要下载，约 150MB-6GB)", flush=True)
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=self.model_dir,
        )
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        beam_size: int = 5,
        **kwargs: object,
    ) -> tuple[list[WordTimestamp], str]:
        """Transcribe audio file and return word-level timestamps with detected language.

        Args:
            audio_path: Path to 16kHz mono WAV file.
            language: Language code (e.g. 'zh', 'en') or None for auto-detect.
            beam_size: Beam size for decoding.
            **kwargs: Additional arguments passed to faster-whisper.

        Returns:
            Tuple of (list of WordTimestamp objects, detected language code).
        """
        model = self._load_model()

        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            word_timestamps=True,
            **kwargs,
        )

        detected_language = info.language
        print(f"🌐 检测到语言: {detected_language} (概率: {info.language_probability:.2%})")

        words: list[WordTimestamp] = []
        for segment in segments:
            seg_words = getattr(segment, "words", None)
            if seg_words is None:
                continue
            for w in seg_words:
                words.append(
                    WordTimestamp(
                        word=w.word.strip(),
                        start=w.start,
                        end=w.end,
                        probability=w.probability,
                    )
                )

        return words, detected_language

    def dump_transcript(
        self, audio_path: Path, output_path: Path, language: str | None = None
    ) -> None:
        """Transcribe and dump full transcript to JSON for debugging."""
        words, detected_lang = self.transcribe(audio_path, language=language)
        data = {
            "language": detected_lang,
            "words": [
                {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                for w in words
            ],
        }
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📄 Transcript 已保存到: {output_path}")


def detect_device() -> str:
    """Detect available compute device and return a human-readable description."""
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return f"CUDA ({name})"
    except ImportError:
        pass

    try:
        from ctranslate2 import get_cuda_device_count  # type: ignore[import-untyped]

        if get_cuda_device_count() > 0:
            return "CUDA (via CTranslate2)"
    except ImportError:
        pass

    import os
    cpu_count = os.cpu_count() or 0
    return f"CPU ({cpu_count} 核) — 建议使用 GPU 以获得更快速度"


def create_transcriber(
    model_size: str = "medium",
    device: str = "auto",
    model_dir: str | None = None,
) -> FasterWhisperTranscriber:
    """Factory to create the default transcriber."""
    compute_type = "auto"
    return FasterWhisperTranscriber(
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        model_dir=model_dir,
    )
