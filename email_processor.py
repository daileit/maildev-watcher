import json
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Tuple

import httpx

import config as env_config
import jsonlog
from database import DatabaseClient
from redis_cache import RedisClient
from telegram import TelegramNotifier

logger = jsonlog.setup_logger("email_processor")

app_config = env_config.Config(group="APP")


class EmailProcessor:
    """MailDev email producer/consumer implementation."""

    def __init__(self, queue_name: str = "mw_incoming_emails"):
        self.maildev_endpoint = self._normalize_maildev_endpoint(app_config.get("APP_MAILDEV_ENDPOINT"))
        self.maildev_timeout = float(app_config.get("APP_MAILDEV_TIMEOUT"))
        self.maildev_receiver_filter = str(app_config.get("APP_MAILDEV_RECEIVER_FILTER") or "").strip().lower()
        self.queue_name = queue_name

        self.redis = RedisClient()
        self.db = DatabaseClient()
        self.telegram = TelegramNotifier()

    def _normalize_maildev_endpoint(self, endpoint: Any) -> str:
        logger.debug(f"Normalizing MailDev endpoint: {endpoint}")
        value = str(endpoint).strip()
        if not value.startswith(("http://", "https://")):
            value = f"http://{value}"
        return value.rstrip("/")

    async def fetch_maildev_email_list(self) -> List[Dict[str, Any]]:
        url = f"{self.maildev_endpoint}/email"
        try:
            async with httpx.AsyncClient(timeout=self.maildev_timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()

            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict) and isinstance(payload.get("emails"), list):
                return payload["emails"]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to fetch email list from {url}: {exc}")

        return []

    async def enqueue_maildev_emails(self) -> int:
        emails = await self.fetch_maildev_email_list()
        for email in emails:
            self.redis.rpush_json(self.queue_name, email)

        if emails:
            logger.info(f"Enqueued {len(emails)} email(s) to {self.queue_name}")

        return len(emails)

    async def process_one_from_queue(self) -> bool:
        items = self.redis.get_list_items(
            self.queue_name,
            count=1,
            pop=True,
            direction="left",
        )
        if not items:
            return False

        email = items[0]
        await self._store_email(email)
        return True

    async def _fetch_mail_detail(self, mailid: str) -> Dict[str, Any]:
        url = f"{self.maildev_endpoint}/email/{mailid}"
        try:
            async with httpx.AsyncClient(timeout=self.maildev_timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to fetch email detail from {url}: {exc}")
        return {}

    async def _delete_maildev_email(self, mailid: str) -> bool:
        url = f"{self.maildev_endpoint}/email/{mailid}"
        try:
            async with httpx.AsyncClient(timeout=self.maildev_timeout) as client:
                response = await client.delete(url)
                response.raise_for_status()
            logger.info(f"Deleted email {mailid} from MailDev")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to delete email {mailid} from {url}: {exc}")
            return False

    def _extract_mailid(self, email: Dict[str, Any]) -> str:
        headers = email.get("headers") if isinstance(email.get("headers"), dict) else {}
        return str(
            email.get("id")
            or email.get("_id")
            or email.get("mailid")
            or email.get("messageId")
            or headers.get("message-id")
            or ""
        ).strip()

    def _format_people(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            values = []
            for item in value:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict):
                    entry = item.get("address") or item.get("email") or item.get("name") or ""
                    if entry:
                        values.append(str(entry))
            return ", ".join(values)
        if isinstance(value, dict):
            return str(value.get("address") or value.get("email") or value.get("name") or "")
        return str(value)

    def _parse_timestamp(self, email: Dict[str, Any]) -> datetime:
        candidates = [
            email.get("time"),
            email.get("createdAt"),
            email.get("date"),
        ]

        for candidate in candidates:
            if not candidate:
                continue

            if isinstance(candidate, (int, float)):
                return datetime.fromtimestamp(candidate)

            if isinstance(candidate, str):
                try:
                    cleaned = candidate.replace("Z", "+00:00")
                    parsed = datetime.fromisoformat(cleaned)
                    if parsed.tzinfo is None:
                        return parsed
                    return parsed.astimezone().replace(tzinfo=None)
                except ValueError:
                    pass

                try:
                    parsed = parsedate_to_datetime(candidate)
                    if parsed.tzinfo is None:
                        return parsed
                    return parsed.astimezone().replace(tzinfo=None)
                except (TypeError, ValueError):
                    pass

        return datetime.now()

    def _build_raw_content(self, email: Dict[str, Any], detail: Dict[str, Any]) -> Tuple[str, str]:
        merged_email = dict(email)
        merged_email.update(detail or {})

        raw_header = ""
        raw_body = ""

        headers = merged_email.get("headers")
        if headers is not None:
            try:
                raw_header = json.dumps(headers, ensure_ascii=False)
            except TypeError:
                raw_header = str(headers)

        body_candidates = [
            merged_email.get("html"),
            merged_email.get("text"),            
            merged_email.get("envelope")
        ]
        for item in body_candidates:
            if item:
                raw_body = str(item)
                break

        if not raw_body:
            try:
                raw_body = json.dumps(merged_email, ensure_ascii=False)
            except TypeError:
                raw_body = str(merged_email)

        return raw_header, raw_body

    def _find_existing_email_id(self, mailid: str, email_time: datetime) -> Any:
        return self.db.fetch_value(
            "SELECT `id` FROM `mw_metadata` WHERE `mailid` = %s AND `timestamp` = %s LIMIT 1",
            (mailid, email_time),
        )

    def _should_drop_by_receiver_filter(self, receiver: str) -> bool:
        if not self.maildev_receiver_filter:
            return False
        return self.maildev_receiver_filter not in receiver.lower()

    async def _store_email(self, email: Dict[str, Any]) -> None:
        mailid = self._extract_mailid(email)
        if not mailid:
            logger.warning("Queue item skipped: missing mail id")
            return

        sender = self._format_people(email.get("from"))
        receiver = self._format_people(email.get("to"))
        if not sender and isinstance(email.get("envelope"), dict):
            sender = str(email.get("envelope", {}).get("from") or "")
        if not receiver and isinstance(email.get("envelope"), dict):
            envelope_to = email.get("envelope", {}).get("to")
            if isinstance(envelope_to, list):
                receiver = ", ".join(str(v) for v in envelope_to if v)
            elif envelope_to:
                receiver = str(envelope_to)

        if self._should_drop_by_receiver_filter(receiver):
            logger.info(
                f"Dropped email {mailid}: receiver '{receiver}' does not contain filter '{self.maildev_receiver_filter}'"
            )
            await self._delete_maildev_email(mailid)
            return

        email_time = self._parse_timestamp(email)
        exists = self._find_existing_email_id(mailid, email_time)
        if exists:
            logger.debug(f"Email {mailid} at {email_time} already stored, skipping")
            await self._delete_maildev_email(mailid)
            return

        subject = str(email.get("subject") or "")

        mail_detail = await self._fetch_mail_detail(mailid)
        raw_header, raw_body = self._build_raw_content(email, mail_detail)
        extracted_content = str(email.get("text") or mail_detail.get("text") or "")

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO `mw_metadata` (`mailid`, `from`, `to`, `timestamp`, `subject`, `extracted_code`, `extracted_content`)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (mailid, sender, receiver, email_time, subject, None, extracted_content),
            )
            cursor.execute(
                """
                INSERT INTO `mw_raw_content` (`mailid`, `raw_header`, `raw_body`)
                VALUES (%s, %s, %s)
                """,
                (mailid, raw_header, raw_body),
            )

        logger.info(f"Stored email {mailid} from {sender} to {receiver}: '{subject}'")
        await self._delete_maildev_email(mailid)
        if self.telegram.is_enabled():
            message = self.telegram.build_new_email_message(subject, sender, receiver, extracted_content.replace("\n", ""))
            await self.telegram.send_message(message)
