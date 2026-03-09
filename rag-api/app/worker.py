"""Ingestion worker — processes jobs from the Redis queue.

Run: python -m app.worker
"""

import logging
import signal
import sys
import time

import redis

from app.db import SessionLocal
from app.services import ingestion, job_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_running = True


def _shutdown(sig: int, frame: object) -> None:
    global _running
    logger.info("Shutdown signal received (sig=%s), draining…", sig)
    _running = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


def main() -> None:
    logger.info("Worker started")
    while _running:
        try:
            doc_id = job_queue.dequeue(timeout=5)
        except redis.ConnectionError as exc:
            logger.error("Redis connection error: %s — retrying in 5s", exc)
            time.sleep(5)
            continue

        if doc_id is None:
            continue

        logger.info("Processing document %s", doc_id)
        try:
            with SessionLocal() as db:
                ingestion.run_ingest_job(doc_id, db)
            logger.info("Document %s ingested successfully", doc_id)
        except Exception:
            logger.exception("Ingestion failed for document %s", doc_id)

    logger.info("Worker stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
