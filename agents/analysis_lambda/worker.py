"""Local worker that processes queued analysis jobs from SQLite."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from agents.analysis_lambda.handler import process_job
from agents.analysis_lambda.models import AnalysisJobPayload
from app.clients.local_queue import SQLiteQueueClient
from app.clients.sqlite_store import SQLiteStore
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AnalysisQueueWorker:
    """Poll the SQLite queue and execute analysis jobs."""

    def __init__(
        self,
        queue_client: SQLiteQueueClient,
        store: SQLiteStore,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._queue = queue_client
        self._store = store
        self._poll_interval = poll_interval_seconds

    async def run_forever(self) -> None:
        while True:
            payload = self._dequeue()
            if payload is None:
                await asyncio.sleep(self._poll_interval)
                continue

            await self._process(payload)

    def _dequeue(self) -> Optional[AnalysisJobPayload]:
        message = self._queue.dequeue_analysis_request()
        if message is None:
            return None
        return message  # already a dict with correct keys

    async def _process(self, payload: AnalysisJobPayload) -> None:
        job_id = payload["job_id"]
        user_id = payload["user_id"]
        logger.info("Dequeued analysis job", extra={"job_id": job_id})

        record_key = {
            "partition_key": f"user#{user_id}",
            "sort_key": f"analysis#{job_id}",
        }
        record = self._store.get_item(**record_key) or {
            "pk": record_key["partition_key"],
            "sk": record_key["sort_key"],
            "user_id": user_id,
            "job_id": job_id,
        }
        record["status"] = "in_progress"
        record["started_at"] = datetime.now(timezone.utc).isoformat()
        self._store.put_item(record)

        try:
            await process_job(payload)
        except Exception:  # pragma: no cover - already logged downstream
            logger.exception("Failed processing analysis job", extra={"job_id": job_id})


async def main(poll_interval_seconds: float = 1.0) -> None:
    settings = get_settings()
    queue_client = SQLiteQueueClient(settings.trade_capture_db_path)
    store = SQLiteStore(settings.trade_capture_db_path)
    worker = AnalysisQueueWorker(
        queue_client=queue_client,
        store=store,
        poll_interval_seconds=poll_interval_seconds,
    )
    await worker.run_forever()


if __name__ == "__main__":  # pragma: no cover - manual execution path
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Analysis queue worker stopped")
