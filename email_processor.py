import json
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Tuple

import httpx

import config as env_config
import jsonlog
from database import DatabaseClient
from redis_cache import RedisClient
from email_ai import EmailAI
from telegram import TelegramNotifier

logger = jsonlog.setup_logger("email_processor")

app_config = env_config.Config(group="APP")


class EmailProcessor:
    """MailDev email producer/consumer implementation."""

    _CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

    def __init__(self, queue_name: str = "mw_incoming_emails"):
        self.maildev_endpoint = self._normalize_maildev_endpoint(app_config.get("APP_MAILDEV_ENDPOINT"))
        self.maildev_timeout = float(app_config.get("APP_MAILDEV_TIMEOUT"))
        self.maildev_receiver_whitelist = str(app_config.get("APP_MAILDEV_RECEIVER_WHITELIST") or "").strip().lower()
        self.maildev_sender_blacklist = str(app_config.get("APP_MAILDEV_SENDER_BLACKLIST") or "").strip().lower()
        self.queue_name = queue_name

        self.redis = RedisClient()
        self.db = DatabaseClient()
        self.telegram = TelegramNotifier()
        self.email_ai = EmailAI()

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

    def _contains_iso2022jp_marker(self, value: Any) -> bool:
        marker = b"\x1b$B"
        if isinstance(value, bytes):
            return marker in value
        if isinstance(value, str):
            return marker.decode("ascii") in value
        return False

    def _decode_iso2022jp(self, value: Any) -> Any:
        if isinstance(value, bytes):
            if not self._contains_iso2022jp_marker(value):
                return value
            try:
                return value.decode("iso-2022-jp")
            except UnicodeDecodeError:
                return value

        if isinstance(value, str):
            if not self._contains_iso2022jp_marker(value):
                return value
            try:
                return value.encode("latin-1").decode("iso-2022-jp")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return value

        if isinstance(value, list):
            return [self._decode_iso2022jp(item) for item in value]

        if isinstance(value, dict):
            return {key: self._decode_iso2022jp(item) for key, item in value.items()}

        return value

    def _build_raw_content(self, email: Dict[str, Any], detail: Dict[str, Any]) -> Tuple[str, str]:
        merged_email = dict(email)
        merged_email.update(detail or {})
        merged_email = self._decode_iso2022jp(merged_email)

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

    def _should_drop_by_receiver_whitelist(self, receiver: str) -> bool:
        if not self.maildev_receiver_whitelist:
            return False
        return self.maildev_receiver_whitelist not in receiver.lower()

    def _should_drop_by_sender_blacklist(self, sender: str) -> bool:
        if not self.maildev_sender_blacklist:
            return False
        return self.maildev_sender_blacklist in sender.lower()

    async def _store_email(self, email: Dict[str, Any]) -> None:
        email = self._decode_iso2022jp(email)
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

        if self._should_drop_by_receiver_whitelist(receiver):
            logger.info(
                f"Dropped email {mailid}: receiver '{receiver}' not in whitelist '{self.maildev_receiver_whitelist}'"
            )
            await self._delete_maildev_email(mailid)
            return

        if self._should_drop_by_sender_blacklist(sender):
            logger.info(
                f"Dropped email {mailid}: sender '{sender}' matched blacklist '{self.maildev_sender_blacklist}'"
            )
            await self._delete_maildev_email(mailid)
            return

        email_time = self._parse_timestamp(email)
        exists = self._find_existing_email_id(mailid, email_time)
        if exists:
            logger.debug(f"Email {mailid} at {email_time} already stored, skipping")
            await self._delete_maildev_email(mailid)
            return

        subject = str(self._decode_iso2022jp(email.get("subject") or ""))

        mail_detail = await self._fetch_mail_detail(mailid)
        mail_detail = self._decode_iso2022jp(mail_detail)
        raw_header, raw_body = self._build_raw_content(email, mail_detail)
        extracted_content = str(self._decode_iso2022jp(email.get("text") or mail_detail.get("text") or ""))
        ai_content = extracted_content or str(self._decode_iso2022jp(email.get("html") or mail_detail.get("html") or ""))
        ai_result = await self.email_ai.summarize(ai_content) if ai_content.strip() else None
        extracted_type = "other"
        extracted_code = None
        if ai_result:
            extracted_type = str(ai_result.get("type") or "other")
            extracted_code = str(ai_result.get("content") or "").strip() or None

        with self.db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO `mw_metadata` (`mailid`, `from`, `to`, `timestamp`, `subject`, `extracted_code`, `extracted_type`, `extracted_content`)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (mailid, sender, receiver, email_time, subject, extracted_code, extracted_type, extracted_content),
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
            notify_content = extracted_code or extracted_content.replace("\n", "")
            message = self.telegram.build_new_email_message(mailid, subject, sender, receiver, notify_content)
            await self.telegram.send_message(message)

    async def get_emails_list(
        self,
        limit: int = 50,
        offset: int = 0,
        mailid: str = None,
        sender: str = None,
        receiver: str = None,
    ) -> Dict[str, Any]:
        """
        Query emails list from database with minimal metadata.
        Returns paginated results with basic email info.
        """
        where_clauses = ["1=1"]
        params = []

        if mailid:
            where_clauses.append("`mailid` LIKE %s")
            params.append(f"%{mailid}%")

        if sender:
            where_clauses.append("`from` LIKE %s")
            params.append(f"%{sender}%")

        if receiver:
            where_clauses.append("`to` LIKE %s")
            params.append(f"%{receiver}%")

        where_sql = " AND ".join(where_clauses)

        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM `mw_metadata` WHERE {where_sql}"
        total = self.db.fetch_value(count_query, params) or 0

        # Get paginated metadata (lightweight)
        metadata_query = f"""
            SELECT `id`, `mailid`, `from`, `to`, `timestamp`, `subject`
            FROM `mw_metadata`
            WHERE {where_sql}
            ORDER BY `timestamp` DESC
            LIMIT %s OFFSET %s
        """
        params_with_pagination = params + [limit, offset]
        metadata_rows = self.db.execute_query(metadata_query, params_with_pagination)

        # Build lightweight email list
        emails = []
        for row in metadata_rows:
            email = {
                "id": row.get("id"),
                "mailid": row.get("mailid"),
                "from": row.get("from") or "",
                "to": row.get("to") or "",
                "timestamp": row.get("timestamp").isoformat() if row.get("timestamp") else None,
                "subject": row.get("subject") or "",
            }
            emails.append(email)

        return {
            "success": True,
            "data": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "count": len(emails),
                "emails": emails,
            },
            "error": None,
        }

    async def get_email_by_mailid(self, mailid: str) -> Dict[str, Any]:
        """
        Fetch a single email by mailid with full metadata and raw content.
        Results are cached for 7 days in Redis.
        """
        # Try to get from cache
        cache_key = f"mw_email:{mailid}"
        cached_result = self.redis.get_json(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache HIT for email {mailid}")
            return cached_result

        metadata = self.db.fetch_one(
            """
            SELECT `id`, `mailid`, `from`, `to`, `timestamp`, `subject`,
                 `extracted_code`, `extracted_type`, `extracted_content`
            FROM `mw_metadata`
            WHERE `mailid` = %s
            LIMIT 1
            """,
            (mailid,),
        )

        if not metadata:
            result = {
                "success": False,
                "data": None,
                "error": f"Email {mailid} not found",
            }
            return result

        raw_content = self.db.fetch_one(
            "SELECT `raw_header`, `raw_body` FROM `mw_raw_content` WHERE `mailid` = %s LIMIT 1",
            (mailid,),
        )

        email = {
            "id": metadata.get("id"),
            "mailid": metadata.get("mailid"),
            "from": metadata.get("from") or "",
            "to": metadata.get("to") or "",
            "timestamp": metadata.get("timestamp").isoformat() if metadata.get("timestamp") else None,
            "subject": metadata.get("subject") or "",
            "extracted_code": metadata.get("extracted_code") or "",
            "extracted_type": metadata.get("extracted_type") or "other",
            "extracted_content": metadata.get("extracted_content") or "",
            "raw": {
                "headers": raw_content.get("raw_header") if raw_content else "",
                "body": raw_content.get("raw_body") if raw_content else "",
            },
        }

        result = {
            "success": True,
            "data": email,
            "error": None,
        }

        # Cache the result for 7 days
        try:
            self.redis.set_json(cache_key, result, ttl=self._CACHE_TTL_SECONDS)
            logger.debug(f"Cached email {mailid} for {self._CACHE_TTL_SECONDS}s")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to cache email {mailid}: {exc}")

        return result
