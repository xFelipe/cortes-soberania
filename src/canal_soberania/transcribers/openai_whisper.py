"""Transcriber via OpenAI Whisper API (escape hatch pago)."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from canal_soberania.logger import logger

_OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"
_MODEL = "whisper-1"


class OpenAIWhisperTranscriber:
    """Chama OpenAI Whisper API com word timestamps.

    Requer OPENAI_API_KEY. Limite de arquivo: 25 MB por request.
    Mesmo formato de response do Groq — reutiliza lógica de parsing.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def transcribe(self, audio_path: Path) -> list[dict[str, Any]]:
        logger.info("OpenAI Whisper: transcrevendo {}...", audio_path.name)

        file_bytes = audio_path.read_bytes()
        boundary = "----FormBoundary7MA4YWxkTrZu0gW"
        filename = audio_path.name

        body_parts: list[bytes] = []
        for name, value in [("model", _MODEL), ("language", "pt"), ("response_format", "verbose_json"), ("timestamp_granularities[]", "word")]:
            body_parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
            )
        body_parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: audio/mpeg\r\n\r\n".encode()
            + file_bytes
            + b"\r\n"
        )
        body_parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(body_parts)

        req = urllib.request.Request(  # noqa: S310
            _OPENAI_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )

        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
            data: dict[str, Any] = json.loads(resp.read())

        words: list[dict[str, Any]] = data.get("words", [])
        segments: list[dict[str, Any]] = []

        if words:
            current: dict[str, Any] = {
                "start": words[0]["start"],
                "end": words[0]["end"],
                "text": words[0]["word"],
                "words": [{"start": words[0]["start"], "end": words[0]["end"], "word": words[0]["word"]}],
            }
            for w in words[1:]:
                gap = w["start"] - current["end"]
                if gap > 1.5 or len(current["text"]) > 500:
                    segments.append(current)
                    current = {"start": w["start"], "end": w["end"], "text": w["word"], "words": [{"start": w["start"], "end": w["end"], "word": w["word"]}]}
                else:
                    current["text"] += " " + w["word"]
                    current["end"] = w["end"]
                    current["words"].append({"start": w["start"], "end": w["end"], "word": w["word"]})
            segments.append(current)
        else:
            text = str(data.get("text", ""))
            if text:
                segments.append({"start": 0.0, "end": float(data.get("duration", 0)), "text": text})

        logger.info("OpenAI Whisper: {} segmentos", len(segments))
        return segments
