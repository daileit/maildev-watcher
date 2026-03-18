import asyncio
from typing import Optional

from openai import OpenAI

import config as env_config
import jsonlog

logger = jsonlog.setup_logger("email_ai")

openai_config = env_config.Config(group="OPENAI")


class EmailAI:
    """Lightweight AI helper for email content summarization."""

    def __init__(self):
        self.api_key = str(openai_config.get("OPENAI_API_KEY") or "").strip()
        self.base_url = str(openai_config.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
        self.model = str(openai_config.get("OPENAI_MODEL") or "gpt-4o").strip().split(",")[0].strip()
        self.language = str(openai_config.get("OPENAI_LANGUAGE") or "English").strip()

    def is_enabled(self) -> bool:
        return bool(self.api_key)

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
        try:
            summary = await asyncio.to_thread(self._summarize_sync, content)
            logger.info(f"AI summary: {summary!r}")
            return summary or None
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"AI summarization failed: {exc}")
            return None
