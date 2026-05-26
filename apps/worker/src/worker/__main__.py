"""SQS polling loop — runs the worker process via `python -m worker`."""
import json
import logging
import signal
import sys

import boto3

from common.config import settings
from worker.tasks import ingest_document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Visibility timeout must be longer than the slowest expected ingestion job.
VISIBILITY_TIMEOUT = 300  # seconds
WAIT_TIME = 20            # long-poll duration (max 20 s)
MAX_MESSAGES = 1          # process one at a time to keep memory predictable

_running = True


def _handle_signal(sig, frame):  # noqa: ANN001
    global _running
    logger.info("Received signal %s — shutting down after current message.", sig)
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _sqs_client():
    endpoint_url = settings.aws_endpoint_url
    if endpoint_url is None and settings.sqs_queue_url.startswith("http://localhost"):
        endpoint_url = "http://localhost:4566"

    kwargs: dict = {
        "region_name": settings.aws_region,
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("sqs", **kwargs)


def main() -> None:
    sqs = _sqs_client()
    queue_url = settings.sqs_queue_url
    logger.info("Worker started — polling %s", queue_url)

    while _running:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=MAX_MESSAGES,
            WaitTimeSeconds=WAIT_TIME,
            VisibilityTimeout=VISIBILITY_TIMEOUT,
        )

        messages = response.get("Messages", [])
        if not messages:
            continue

        for msg in messages:
            receipt = msg["ReceiptHandle"]
            try:
                payload = json.loads(msg["Body"])
                document_id = payload["document_id"]
                logger.info("Processing document %s", document_id)
                ingest_document(document_id)
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
                logger.info("Finished document %s", document_id)
            except Exception:
                logger.exception(
                    "Failed to process message %s — leaving in queue for visibility timeout retry",
                    msg.get("MessageId"),
                )

    logger.info("Worker stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
