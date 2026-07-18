"""Failure-tolerant Django cache backend.

Redis is an optional acceleration layer.  A cache outage must behave as a
cache miss and must never make an API request fail.
"""

import logging

from django.core.cache.backends.redis import RedisCache


logger = logging.getLogger(__name__)


class ResilientRedisCache(RedisCache):
    """RedisCache that degrades to cache misses/no-op writes on outages."""

    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default=default, version=version)
        except Exception as exc:
            logger.warning("Django cache read failed for %s: %s", key, exc)
            return default

    def set(self, key, value, timeout=None, version=None):
        try:
            return super().set(key, value, timeout=timeout, version=version)
        except Exception as exc:
            logger.warning("Django cache write failed for %s: %s", key, exc)
            return False

    def add(self, key, value, timeout=None, version=None):
        try:
            return super().add(key, value, timeout=timeout, version=version)
        except Exception as exc:
            logger.warning("Django cache add failed for %s: %s", key, exc)
            return False

    def delete(self, key, version=None):
        try:
            return super().delete(key, version=version)
        except Exception as exc:
            logger.warning("Django cache delete failed for %s: %s", key, exc)
            return False

    def get_many(self, keys, version=None):
        try:
            return super().get_many(keys, version=version)
        except Exception as exc:
            logger.warning("Django cache multi-read failed: %s", exc)
            return {}

    def set_many(self, data, timeout=None, version=None):
        try:
            return super().set_many(data, timeout=timeout, version=version)
        except Exception as exc:
            logger.warning("Django cache multi-write failed: %s", exc)
            return list(data)

    def delete_many(self, keys, version=None):
        try:
            return super().delete_many(keys, version=version)
        except Exception as exc:
            logger.warning("Django cache multi-delete failed: %s", exc)
            return False

    def clear(self):
        try:
            return super().clear()
        except Exception as exc:
            logger.warning("Django cache clear failed: %s", exc)
            return False
