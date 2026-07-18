"""Redis-backed application cache abstraction for DigiHMS.

All application caching must go through :class:`CeliyoCache`. Direct use of
``django.core.cache`` is not allowed by project rules.

The application cache uses Redis database 0 (see ``CACHES`` in settings).
Celery broker and rate-limiting caches use separate databases.
"""

import json
import logging
from urllib.parse import urlparse

import redis
from django.conf import settings


logger = logging.getLogger(__name__)


class CeliyoCache:
    """Thin Redis wrapper for DigiHMS caching needs.

    Defaults are read from Django settings:
        - ``CELERY_BROKER_URL`` is parsed to obtain the Redis host/port/db
          unless ``REDIS_CACHE_URL`` is provided.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        # Keep a process-level singleton to avoid connection churn.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = None
        return cls._instance

    def __init__(self, url=None, decode_responses=True):
        if url is None:
            url = getattr(settings, "REDIS_CACHE_URL", None)
        if url is None:
            broker = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
            parsed = urlparse(broker)
            url = f"redis://{parsed.hostname or 'localhost'}:{parsed.port or 6379}/0"
        self.url = url
        self.decode_responses = decode_responses

    def _get_client(self):
        if self._client is None:
            # Cache is an optional acceleration layer.  Keep outages from
            # adding multi-second connection waits to guarded DB fallbacks.
            connect_timeout = float(
                getattr(settings, "REDIS_CACHE_CONNECT_TIMEOUT", 0.5)
            )
            socket_timeout = float(
                getattr(settings, "REDIS_CACHE_SOCKET_TIMEOUT", 0.5)
            )
            self._client = redis.from_url(
                self.url,
                decode_responses=self.decode_responses,
                socket_connect_timeout=connect_timeout,
                socket_timeout=socket_timeout,
                retry_on_timeout=False,
            )
        return self._client

    def get(self, key, default=None):
        """Fetch a cached value. JSON-encoded strings are decoded automatically."""
        try:
            value = self._get_client().get(key)
        except (redis.RedisError, OSError) as exc:
            logger.warning("Redis cache read failed for %s: %s", key, exc)
            return default
        if value is None:
            return default
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def set(self, key, value, ttl=None):
        """Store ``value`` under ``key``. ``ttl`` is in seconds."""
        if not isinstance(value, (str, bytes)):
            value = json.dumps(value, default=str)
        try:
            return bool(self._get_client().set(key, value, ex=ttl))
        except (redis.RedisError, OSError) as exc:
            logger.warning("Redis cache write failed for %s: %s", key, exc)
            return False

    def delete(self, key):
        """Delete a single key."""
        try:
            return self._get_client().delete(key)
        except (redis.RedisError, OSError) as exc:
            logger.warning("Redis cache delete failed for %s: %s", key, exc)
            return 0

    def delete_pattern(self, pattern):
        """Delete all keys matching ``pattern`` (uses SCAN to avoid blocking)."""
        try:
            client = self._get_client()
            deleted = 0
            for key in client.scan_iter(match=pattern):
                deleted += client.delete(key)
            return deleted
        except (redis.RedisError, OSError) as exc:
            logger.warning("Redis cache pattern delete failed for %s: %s", pattern, exc)
            return 0

    def exists(self, key):
        """Return True if the key exists."""
        try:
            return bool(self._get_client().exists(key))
        except (redis.RedisError, OSError) as exc:
            logger.warning("Redis cache exists check failed for %s: %s", key, exc)
            return False

    def ttl(self, key):
        """Return remaining TTL in seconds."""
        try:
            return self._get_client().ttl(key)
        except (redis.RedisError, OSError) as exc:
            logger.warning("Redis cache TTL check failed for %s: %s", key, exc)
            return -2
