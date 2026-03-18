from typing import List

import httpx

import config as env_config
import jsonlog

logger = jsonlog.setup_logger("telegram")

telegram_config = env_config.Config()


class TelegramNotifier:
    """Send Telegram notifications for processed emails."""

    def __init__(self):
        self.bot_token = str(telegram_config.get("TELEGRAM_BOT_TOKEN") or "").strip()
        raw_chat_ids = str(telegram_config.get("TELEGRAM_CHAT_IDS") or "")
        self.chat_ids = [item.strip() for item in raw_chat_ids.split(",") if item.strip()]
        self.timeout = float(telegram_config.get("APP_MAILDEV_TIMEOUT") or 10)

    def is_enabled(self) -> bool:
        return bool(self.bot_token and self.chat_ids)

    def build_new_email_message(self, subject: str, sender: str, receiver: str, content: str) -> str:
        message_lines = [
            "New email received! Details:",
            f"Subject: {subject or '-'}",
            f"From: {sender or '-'}",
            f"To: {receiver or '-'}",
            f"Content: {content or '-'}",
        ]
        return "\n".join(message_lines)

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
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to send Telegram message to chat {chat_id}: {exc}")
