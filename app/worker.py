"""SQS worker: takes 'create_library' jobs from the queue and writes them to MySQL.

SQS delivers at least once, so the same message can arrive twice. The job id is stored in
processed_jobs in the same transaction as the library, and a repeated job is skipped.
"""
import json
import logging
import os
import signal
import time

from sqlalchemy.exc import IntegrityError

from app import app
from library import db, jobs, sqs
from library.models import Library, ProcessedJob

log = logging.getLogger("worker")

# Pause before each write to imitate a slow operation (e.g. a call to an external catalogue).
DELAY = int(os.environ.get("WORKER_DELAY_MS", "200")) / 1000

running = True


def stop(*_):
    global running
    running = False
    log.info("stop requested, finishing the current batch")


def create_library(job_id, data):
    done = db.session.get(ProcessedJob, job_id)
    if done:
        log.info("job %s was already processed (library %s), skipping", job_id, done.library_id)
        return "done", {"library_id": done.library_id, "duplicate_delivery": True}

    time.sleep(DELAY)

    lib = Library(name=data["name"], address=data["address"], city=data["city"], phone=data["phone"])
    db.session.add(lib)
    try:
        db.session.flush()
        db.session.add(ProcessedJob(job_id=job_id, library_id=lib.id))
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        done = db.session.get(ProcessedJob, job_id)
        if done:
            return "done", {"library_id": done.library_id, "duplicate_delivery": True}
        # e.g. the phone is already taken: a business error, retrying will not help
        return "failed", {"error": str(e.orig)}
    return "done", {"library_id": lib.id, "result": lib.to_dict()}


HANDLERS = {"create_library": create_library}


def handle(message):
    body = json.loads(message["Body"])
    job_id = body["job_id"]
    attempt = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
    handler = HANDLERS.get(body.get("op"))
    if handler is None:
        log.error("job %s has unknown op %r, dropping", job_id, body.get("op"))
        jobs.save(job_id, "failed", attempt=attempt, error="unknown operation")
        return

    jobs.save(job_id, "processing", attempt=attempt)
    with app.app_context():
        try:
            status, fields = handler(job_id, body["data"])
        finally:
            db.session.remove()
    jobs.save(job_id, status, attempt=attempt, **fields)
    log.info("job %s -> %s (attempt %s)", job_id, status, attempt)


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    client = sqs.client()
    log.info("worker started, queue=%s delay=%ss", sqs.QUEUE_URL, DELAY)
    while running:
        resp = client.receive_message(
            QueueUrl=sqs.QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            AttributeNames=["ApproximateReceiveCount"],
        )
        for message in resp.get("Messages", []):
            try:
                handle(message)
            except Exception:
                # not deleted → visible again after the visibility timeout; after 5 tries → DLQ
                log.exception("message %s failed, it will be redelivered", message["MessageId"])
                continue
            client.delete_message(QueueUrl=sqs.QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])


if __name__ == "__main__":
    main()
