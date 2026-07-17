from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from common.middleware import ActivityLogMiddleware


class ActivityLogMiddlewareTests(SimpleTestCase):
    @patch("common.middleware._enqueue_activity_log")
    def test_clinical_response_queues_audit_without_publishing_inline(self, enqueue):
        response = SimpleNamespace(status_code=200)
        request = SimpleNamespace(
            path="/api/clinical/encounters/opd_visit/2401/forms/",
            tenant_id="tenant-1",
            user_id="user-1",
            method="GET",
            META={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "test"},
        )

        returned = ActivityLogMiddleware(lambda _: response).process_response(
            request, response
        )

        self.assertIs(returned, response)
        enqueue.assert_called_once_with(
            {
                "tenant_id": "tenant-1",
                "user_id": "user-1",
                "method": "GET",
                "path": request.path,
                "status_code": 200,
                "ip_address": "127.0.0.1",
                "user_agent": "test",
            }
        )
