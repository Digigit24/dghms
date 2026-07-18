from types import SimpleNamespace
from unittest.mock import Mock, patch

import redis
from django.core.cache.backends.redis import RedisCache
from django.http import QueryDict
from django.test import SimpleTestCase
from rest_framework.mixins import ListModelMixin
from rest_framework.response import Response

from apps.clinical.views import ClinicalFormViewSet
from common.cache import CeliyoCache
from common.cache_backend import ResilientRedisCache
from common.celery_utils import enqueue_task, get_task_snapshot


class CacheResilienceTests(SimpleTestCase):
    def test_celiyo_cache_treats_redis_error_as_miss(self):
        cache = CeliyoCache(url="redis://localhost:6379/15")
        cache._client = Mock()
        cache._client.get.side_effect = redis.TimeoutError("redis unavailable")

        self.assertEqual(cache.get("key", default="fallback"), "fallback")

    @patch.object(RedisCache, "get", side_effect=TimeoutError("redis unavailable"))
    def test_django_cache_backend_treats_error_as_miss(self, _get):
        cache = ResilientRedisCache("redis://localhost:6379/15", {})

        self.assertEqual(cache.get("key", default="fallback"), "fallback")

    @patch.object(ListModelMixin, "list", return_value=Response({"results": []}))
    @patch("apps.clinical.views.CeliyoCache")
    def test_clinical_form_list_falls_back_to_database(self, cache_class, _list):
        cache_class.return_value.get.side_effect = redis.TimeoutError(
            "redis unavailable"
        )
        request = SimpleNamespace(
            query_params=QueryDict("page_size=200"),
            tenant_id="tenant-1",
        )

        response = ClinicalFormViewSet().list(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"results": []})

    def test_task_publish_failure_is_controlled(self):
        task = Mock()
        task.name = "test.task"
        task.apply_async.side_effect = ConnectionError("redis unavailable")

        self.assertIsNone(enqueue_task(task, value=1))
        task.apply_async.assert_called_once_with(kwargs={"value": 1}, retry=False)

    @patch("common.celery_utils.AsyncResult")
    def test_result_backend_failure_is_controlled(self, async_result):
        type(async_result.return_value).state = property(
            lambda _self: (_ for _ in ()).throw(ConnectionError("redis unavailable"))
        )

        self.assertIsNone(get_task_snapshot("task-id"))
