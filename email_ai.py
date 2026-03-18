import asyncio
import re
import random
from typing import Optional

from openai import OpenAI

import config as env_config
import jsonlog
from redis_cache import RedisClient

logger = jsonlog.setup_logger("email_ai")

openai_config = env_config.Config(group="OPENAI")


class EmailAI:
    """Lightweight AI helper for email content summarization."""

    _FAILED_MODEL_TTL_SECONDS = 3600
    _MAX_AI_ATTEMPTS = 3
    _MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^\)]+\)", re.IGNORECASE)
    _HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
    _IMAGE_URL_RE = re.compile(r"https?://\S+\.(?:png|jpe?g|gif|webp|svg|bmp)(?:\?\S*)?", re.IGNORECASE)
    _SPACE_RE = re.compile(r"[ \t]{2,}")
    _NEWLINE_RE = re.compile(r"\n{3,}")

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = str(openai_config.get("OPENAI_API_KEY") or "").strip()
        self.model_config = model or openai_config.get("OPENAI_MODELS", "gpt-4o")
        self.base_url = base_url or openai_config.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.language = str(openai_config.get("OPENAI_LANGUAGE") or "English").strip()

        if not self.api_key:
            logger.warning("OpenAI API key not configured; EmailAI is disabled")
            self.client = None
            self.model_list = ["gpt-4o"]
            self.redis = None
            return

        self.model_list = [m.strip() for m in str(self.model_config).split(",") if m.strip()]
        if not self.model_list:
            self.model_list = ["gpt-4o"]

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        try:
            self.redis = RedisClient()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Redis client initialization failed: {exc}. Model ignore cache disabled.")
            self.redis = None

        if len(self.model_list) > 1:
            logger.info(
                f"EmailAI initialized with base_url: {self.base_url}, "
                f"models: {self.model_list} (random selection enabled)"
            )
        else:
            logger.info(
                f"EmailAI initialized with base_url: {self.base_url}, "
                f"model: {self.model_list[0]}"
            )

    def is_enabled(self) -> bool:
        return self.client is not None

    def _get_model(self, ignore_model: str = "") -> str:
        if ignore_model and self.redis:
            ignore_key = f"maildev_watcher:ignored_model:{ignore_model}"
            try:
                self.redis.set_string(ignore_key, "1", ttl=self._FAILED_MODEL_TTL_SECONDS)
                logger.info(
                    f"Cached ignored model: {ignore_model} (TTL: {self._FAILED_MODEL_TTL_SECONDS}s)"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to cache ignored model {ignore_model}: {exc}")

        if len(self.model_list) == 1:
            return self.model_list[0]

        max_attempts = len(self.model_list)
        for _ in range(max_attempts):
            selected_model = random.choice(self.model_list)
            if self.redis:
                ignore_key = f"maildev_watcher:ignored_model:{selected_model}"
                try:
                    if self.redis.get_string(ignore_key):
                        continue
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to check ignore cache for {selected_model}: {exc}")

            logger.debug(f"Selected model: {selected_model} from {self.model_list}")
            return selected_model

        selected_model = random.choice(self.model_list)
        logger.warning(f"All models are ignored. Returning random model anyway: {selected_model}")
        return selected_model

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
        if not self.client:
            return ""

        last_exc = None
        ignore_model = ""

        for _ in range(self._MAX_AI_ATTEMPTS):
            selected_model = self._get_model(ignore_model=ignore_model)
            try:
                logger.info(f"Calling OpenAI API with model {selected_model}")
                response = self.client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                f"You are an email assistant. Summarize the email content in one super short sentence "
                                f"that captures the very main information only. Reply in {self.language}. "
                                f"Output only the summary sentence, nothing else, no reasoning."
                            ),
                        },
                        {"role": "user", "content": content},
                    ],
                    max_tokens=2048,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                if response.choices and response.choices[0].message and response.choices[0].message.content:
                    return (response.choices[0].message.content).strip()
                else:
                    logger.warning(f"OpenAI API response missing content with model {selected_model}: {response}")
                    return ""
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                ignore_model = selected_model
                logger.warning(f"AI call failed with model {selected_model}: {exc}")

        if last_exc:
            raise last_exc
        return ""

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
