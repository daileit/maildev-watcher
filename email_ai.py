import asyncio
import re
from typing import Optional

from openai import OpenAI

import config as env_config
import jsonlog

logger = jsonlog.setup_logger("email_ai")

openai_config = env_config.Config(group="OPENAI")


class EmailAI:
    """Lightweight AI helper for email content summarization."""

    _MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^\)]+\)", re.IGNORECASE)
    _HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
    _IMAGE_URL_RE = re.compile(r"https?://\S+\.(?:png|jpe?g|gif|webp|svg|bmp)(?:\?\S*)?", re.IGNORECASE)
    _SPACE_RE = re.compile(r"[ \t]{2,}")
    _NEWLINE_RE = re.compile(r"\n{3,}")

    def __init__(self):
        self.api_key = str(openai_config.get("OPENAI_API_KEY") or "").strip()
        self.base_url = str(openai_config.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
        self.model = str(openai_config.get("OPENAI_MODEL") or "gpt-4o").strip().split(",")[0].strip()
        self.language = str(openai_config.get("OPENAI_LANGUAGE") or "English").strip()

    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def _prepare_content(self, content: str) -> str:
        cleaned = self._MARKDOWN_IMAGE_RE.sub(" ", content)
        cleaned = self._HTML_IMAGE_RE.sub(" ", cleaned)
        cleaned = self._IMAGE_URL_RE.sub(" ", cleaned)
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        lines = [self._SPACE_RE.sub(" ", line).strip() for line in cleaned.split("\n")]
        cleaned = "\n".join(lines)
        cleaned = self._NEWLINE_RE.sub("\n\n", cleaned).strip()

        words = cleaned.split()
        if len(words) > 3900:
            cleaned = " ".join(words[:3900])

        return cleaned

    def _summarize_sync(self, content: str) -> str:
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are an email assistant. Summarize the email content in one short sentence "
                        f"that captures the main information. Reply in {self.language}. "
                        f"Output only the summary sentence, nothing else."
                    ),
                },
                {"role": "user", "content": content},
            ],
            max_tokens=100,
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()

    async def summarize(self, content: str) -> Optional[str]:
        if not self.is_enabled():
            logger.debug("EmailAI disabled: OPENAI_API_KEY not configured")
            return None
        if not content.strip():
            return None
        prepared_content = self._prepare_content(content)
        if not prepared_content:
            return None
        try:
            summary = await asyncio.to_thread(self._summarize_sync, prepared_content)
            logger.info(f"AI summary: {summary!r}")
            return summary or None
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"AI summarization failed: {exc}")
            return None
