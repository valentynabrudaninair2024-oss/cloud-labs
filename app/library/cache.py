"""Cache-aside helpers. Any Redis failure falls back to the database instead of failing the request."""
import json
import logging
import os

import redis

from library.redis_client import get_client

log = logging.getLogger(__name__)

ENABLED = os.environ.get("CACHE_ENABLED", "false").lower() in ("1", "true", "yes")
TTL = int(os.environ.get("CACHE_TTL", "45"))


def _client():
    return get_client() if ENABLED else None


def get_json(key):
    """Return (value, status) where status is HIT, MISS, BYPASS (cache off) or ERROR."""
    client = _client()
    if client is None:
        return None, "BYPASS"
    try:
        raw = client.get(key)
    except redis.RedisError as e:
        log.warning("cache get %s failed: %s", key, e)
        return None, "ERROR"
    if raw is None:
        return None, "MISS"
    return json.loads(raw), "HIT"


def set_json(key, value):
    client = _client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=TTL)
    except redis.RedisError as e:
        log.warning("cache set %s failed: %s", key, e)


def stats():
    info = {"enabled": ENABLED, "ttl": TTL}
    client = _client()
    if client is None:
        return info
    try:
        s = client.info("stats")
        info.update(hits=s.get("keyspace_hits"), misses=s.get("keyspace_misses"))
    except redis.RedisError as e:
        info["error"] = str(e)
    return info
