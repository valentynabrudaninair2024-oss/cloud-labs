"""Idempotency-Key support for POST endpoints.

The first request with a key takes a short lock in Redis, runs, and stores its response for 24 h.
A repeat with the same key and body gets the stored response (header Idempotent-Replayed: true).
The same key with a different body → 422; while the first request is still running → 409.
5xx responses are not stored, so the client may retry. If Redis is down the request just runs.
"""
import hashlib
import json
import logging
from functools import wraps

import redis
from flask import Response, jsonify, make_response, request

from library.redis_client import get_client

log = logging.getLogger(__name__)

HEADER = "Idempotency-Key"
RESULT_TTL = 24 * 3600
LOCK_TTL = 60


def _fingerprint():
    h = hashlib.sha256()
    h.update(request.method.encode())
    h.update(request.path.encode())
    h.update(request.get_data() or b"")
    return h.hexdigest()


def _replay(stored):
    resp = Response(stored["body"], status=stored["status"], mimetype="application/json")
    if stored.get("location"):
        resp.headers["Location"] = stored["location"]
    resp.headers["Idempotent-Replayed"] = "true"
    return resp


def _in_progress():
    resp = jsonify({"error": "A request with this key is still being processed"})
    resp.status_code = 409
    resp.headers["Retry-After"] = "1"
    return resp


def idempotent(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        key = request.headers.get(HEADER)
        if not key:
            return view(*args, **kwargs)
        if len(key) > 255:
            return jsonify({"error": f"{HEADER} must be at most 255 characters"}), 400

        r = get_client()
        if r is None:
            return view(*args, **kwargs)

        rkey = f"idem:{request.path}:{key}"
        fp = _fingerprint()
        try:
            locked = r.set(rkey, json.dumps({"state": "in_progress", "fp": fp}), nx=True, ex=LOCK_TTL)
            if not locked:
                raw = r.get(rkey)
                stored = json.loads(raw) if raw else None
                if stored is None or stored["state"] == "in_progress":
                    if stored and stored["fp"] != fp:
                        return jsonify({"error": f"{HEADER} was already used with a different request"}), 422
                    return _in_progress()
                if stored["fp"] != fp:
                    return jsonify({"error": f"{HEADER} was already used with a different request"}), 422
                return _replay(stored)
        except redis.RedisError as e:
            log.warning("idempotency store unavailable, running without it: %s", e)
            return view(*args, **kwargs)

        try:
            resp = make_response(view(*args, **kwargs))
        except Exception:
            r.delete(rkey)
            raise

        try:
            if resp.status_code >= 500:
                r.delete(rkey)
            else:
                r.set(rkey, json.dumps({
                    "state": "done",
                    "fp": fp,
                    "status": resp.status_code,
                    "body": resp.get_data(as_text=True),
                    "location": resp.headers.get("Location"),
                }), ex=RESULT_TTL)
        except redis.RedisError as e:
            log.warning("could not store idempotent response: %s", e)
        return resp

    return wrapper
