import asyncio
from typing import List

import config as env_config
import jsonlog
from email_processor import EmailProcessor

logger = jsonlog.setup_logger("background_tasks")

app_config = env_config.Config(group="APP")


class BackgroundTaskRunner:
    """Runs periodic background loops and delegates processing to EmailProcessor."""

    def __init__(self):
        self.crawler_delay = int(app_config.get("APP_CRAWLER_DELAY", "30"))
        self.worker_delay = float(app_config.get("APP_QUEUE_WORKER_DELAY", "5"))

        self.processor = EmailProcessor(queue_name="mw_incoming_emails")

        self._stop_event = asyncio.Event()
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        """Start all background loops."""
        if self._tasks:
            return

        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self._producer_loop(), name="maildev-producer"),
            asyncio.create_task(self._consumer_loop(), name="maildev-consumer"),
        ]
        logger.info("Background tasks started")

    async def stop(self) -> None:
        """Stop all background loops."""
        if not self._tasks:
            return

        self._stop_event.set()
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("Background tasks stopped")

    async def _producer_loop(self) -> None:
        """Periodically fetch MailDev email list and enqueue each email JSON."""
        while not self._stop_event.is_set():
            try:
                await self.processor.enqueue_maildev_emails()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(f"MailDev producer loop error: {exc}")

            await asyncio.sleep(self.crawler_delay)

    async def _consumer_loop(self) -> None:
        """Continuously pop queue items and persist metadata + raw content."""
        while not self._stop_event.is_set():
            try:
                processed = await self.processor.process_one_from_queue()
                if not processed:
                    await asyncio.sleep(self.worker_delay)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Queue consumer loop error: {exc}")
                await asyncio.sleep(self.worker_delay)


runner = BackgroundTaskRunner()


async def start_background_tasks() -> None:
    await runner.start()


async def stop_background_tasks() -> None:
    await runner.stop()
