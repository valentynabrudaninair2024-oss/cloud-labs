"""Idempotency-Key on POST /libraries and POST /libraries/async, and duplicate SQS delivery."""
import json
import os
import time
import uuid

import pytest
import requests

from conftest import new_library, url

SQS_ENDPOINT_URL = os.environ.get("SQS_ENDPOINT_URL", "http://localhost:9324")
QUEUE_URL = os.environ.get("QUEUE_URL", "http://localhost:9324/000000000000/library-writes")


def inserts():
    return requests.get(url("/stats"), timeout=5).json()["db"]["Com_insert"]


def wait_job(job_id, timeout=30, until=lambda job: job["status"] in ("done", "failed")):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = requests.get(url(f"/jobs/{job_id}"), timeout=5).json()
        if until(job):
            return job
        time.sleep(0.5)
    pytest.fail(f"job {job_id} did not finish in {timeout}s")


def post(path, body, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return requests.post(url(path), json=body, headers=headers, timeout=5)


def test_same_key_creates_one_library_and_replays_response():
    key, body = str(uuid.uuid4()), new_library()
    before = inserts()

    first = post("/libraries", body, key)
    second = post("/libraries", body, key)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert inserts() - before == 1


def test_without_key_repeat_is_executed_again():
    body = new_library()
    assert post("/libraries", body).status_code == 201
    assert post("/libraries", body).status_code == 409  # same phone


def test_same_key_with_other_body_is_rejected():
    key = str(uuid.uuid4())
    assert post("/libraries", new_library(), key).status_code == 201
    assert post("/libraries", new_library(), key).status_code == 422


def test_async_same_key_enqueues_once():
    key, body = str(uuid.uuid4()), new_library()
    before = inserts()

    first = post("/libraries/async", body, key)
    second = post("/libraries/async", body, key)
    assert first.status_code == 202 and second.status_code == 202
    assert second.json() == first.json()

    job = wait_job(first.json()["job_id"])
    assert job["status"] == "done"
    assert job["result"]["phone"] == body["phone"]
    assert inserts() - before == 2  # library + processed_jobs row


def test_worker_skips_redelivered_message():
    boto3 = pytest.importorskip("boto3")
    if not any(h in SQS_ENDPOINT_URL for h in ("localhost", "127.0.0.1")):
        pytest.skip("needs direct access to the local queue")
    client = boto3.client("sqs", region_name="eu-central-1", endpoint_url=SQS_ENDPOINT_URL,
                          aws_access_key_id="local", aws_secret_access_key="local")

    created = post("/libraries/async", new_library()).json()
    job = wait_job(created["job_id"])
    assert job["status"] == "done"
    library_id = job["library_id"]
    before = inserts()

    client.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(
        {"job_id": created["job_id"], "op": "create_library", "data": new_library()}))
    job = wait_job(created["job_id"], until=lambda j: j.get("duplicate_delivery"))

    assert job["library_id"] == library_id
    assert inserts() - before == 0
