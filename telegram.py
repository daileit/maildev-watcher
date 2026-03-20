import re
import asyncio

import config as env_config
import jsonlog
from telebot import TeleBot

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
        self.bot = TeleBot(self.bot_token) if self.bot_token else None

    def is_enabled(self) -> bool:
        return bool(self.bot and self.chat_ids)

    def _escape_markdown_v2(self, text: str) -> str:
        escaped = self._CONTROL_CHAR_RE.sub(" ", text or "")
        escaped = self._MARKDOWN_SPECIAL_RE.sub(r"\\\1", escaped)
        escaped = re.sub(r"\s{2,}", " ", escaped)
        escaped = re.sub(r"\n{3,}", "\n\n", escaped)
        return escaped.strip()

    def build_new_email_message(self, mailid: str, subject: str, sender: str, receiver: str, content: str) -> str:
        safe_mailid = self._escape_markdown_v2(mailid or "-")
        safe_subject = self._escape_markdown_v2(subject or "-")
        safe_sender = self._escape_markdown_v2(sender or "-")
        safe_receiver = self._escape_markdown_v2(receiver or "-")
        safe_content = self._escape_markdown_v2(content or "-")

        message_lines = [
            f"⛑ 📨 *New email received\! ID: *`{safe_mailid}`",
            f"*Subject:* {safe_subject}",
            f"*From:* {safe_sender}",
            f"*To:* {safe_receiver}",
            f"*Content:* {safe_content}",
        ]
        return "\n".join(message_lines)

    def _sanitize_message(self, message: str) -> str:
        sanitized = self._CONTROL_CHAR_RE.sub(" ", message)
        sanitized = re.sub(r"\s{2,}", " ", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        return sanitized.strip()

    async def send_message(self, message: str) -> None:
        if not self.is_enabled():
            logger.debug("Telegram notifier disabled: missing bot token or chat ids")
            return

        for chat_id in self.chat_ids:
            try:
                await asyncio.to_thread(
                    self.bot.send_message,
                    chat_id,
                    message,
                    parse_mode="MarkdownV2",
                    disable_web_page_preview=True,
                    timeout=self.timeout,
                )
            except Exception as exc:  # noqa: BLE001
                sanitized_message = self._sanitize_message(message)
                if not sanitized_message:
                    logger.warning(f"Failed to send Telegram message to chat {chat_id}: {exc}")
                    continue

                try:
                    await asyncio.to_thread(
                        self.bot.send_message,
                        chat_id,
                        sanitized_message,
                        disable_web_page_preview=True,
                        timeout=self.timeout,
                    )
                except Exception as retry_exc:  # noqa: BLE001
                    logger.warning(
                        f"Failed to send Telegram message to chat {chat_id}: {retry_exc}"
                    )
