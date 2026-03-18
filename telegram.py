import re
from typing import List

import httpx

import config as env_config
import jsonlog

logger = jsonlog.setup_logger("telegram")

telegram_config = env_config.Config()


class TelegramNotifier:
    """Send Telegram notifications for processed emails."""

    _CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
    _MARKDOWN_SPECIAL_RE = re.compile(r"([_\*\[\]\(\)~`>#+\-=\|\{\}\.\!])")

    def __init__(self):
        self.bot_token = str(telegram_config.get("TELEGRAM_BOT_TOKEN") or "").strip()
        raw_chat_ids = str(telegram_config.get("TELEGRAM_CHAT_IDS") or "")
        self.chat_ids = [item.strip() for item in raw_chat_ids.split(",") if item.strip()]
        self.timeout = float(telegram_config.get("APP_MAILDEV_TIMEOUT") or 10)

    def is_enabled(self) -> bool:
        return bool(self.bot_token and self.chat_ids)

    def build_new_email_message(self, subject: str, sender: str, receiver: str, content: str) -> str:
        message_lines = [
            "⛑ 📨 New email received! ",
            f"*Subject: {subject or '-'}*",
            f"From: {sender or '-'}",
            f"To: {receiver or '-'}",
            f"Content: {content or '-'}",
        ]
        return "\n".join(message_lines)

    def _sanitize_message(self, message: str) -> str:
        sanitized = self._CONTROL_CHAR_RE.sub(" ", message)
        sanitized = self._MARKDOWN_SPECIAL_RE.sub(r"\\\1", sanitized)
        sanitized = re.sub(r"\s{2,}", " ", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        return sanitized.strip()

    async def send_message(self, message: str) -> None:
        if not self.is_enabled():
            logger.debug("Telegram notifier disabled: missing bot token or chat ids")
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for chat_id in self.chat_ids:
                try:
                    response = await client.post(
                        url,
                        json={
                            "chat_id": chat_id,
                            "text": message,
                        },
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 400:
                        logger.warning(f"Failed to send Telegram message to chat {chat_id}: {exc}")
                        continue

                    sanitized_message = self._sanitize_message(message)
                    if not sanitized_message or sanitized_message == message:
                        logger.warning(f"Failed to send Telegram message to chat {chat_id}: {exc}")
                        continue

                    try:
                        retry_response = await client.post(
                            url,
                            json={
                                "chat_id": chat_id,
                                "text": sanitized_message,
                            },
                        )
                        retry_response.raise_for_status()
                    except Exception as retry_exc:  # noqa: BLE001
                        logger.warning(
                            f"Failed to send sanitized Telegram message to chat {chat_id}: {retry_exc}"
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to send Telegram message to chat {chat_id}: {exc}")
