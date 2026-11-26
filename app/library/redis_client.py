"""One shared Redis/Valkey connection for cache, idempotency keys and job statuses."""
import os

import redis

_client = None


def get_client():
    """Return the client, or None when REDIS_URL is not set (the API still works without Redis)."""
    global _client
    url = os.environ.get("REDIS_URL")
    if _client is None and url:
        _client = redis.Redis.from_url(
            url,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
            health_check_interval=30,
        )
    return _client
