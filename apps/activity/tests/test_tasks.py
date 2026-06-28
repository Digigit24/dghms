"""Tests for activity log task."""

import uuid

from django.test import TestCase

from apps.activity.models import UserActivityLog
from apps.activity.tasks import write_activity_log_entry


class WriteActivityLogEntryTest(TestCase):
    def test_creates_log_row(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        write_activity_log_entry(
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            method="GET",
            path="/api/clinical/forms/",
            status_code=200,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        log = UserActivityLog.objects.get()
        self.assertEqual(log.method, "GET")
        self.assertEqual(log.path, "/api/clinical/forms/")
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.tenant_id, tenant_id)
        self.assertEqual(log.user_id, user_id)

    def test_handles_missing_user(self):
        tenant_id = uuid.uuid4()
        write_activity_log_entry(
            tenant_id=str(tenant_id),
            user_id=None,
            method="GET",
            path="/api/clinical/forms/",
            status_code=401,
            ip_address="",
            user_agent="",
        )
        log = UserActivityLog.objects.get()
        self.assertIsNone(log.user_id)
        self.assertEqual(log.status_code, 401)

    def test_scrubs_query_string_from_path(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        write_activity_log_entry(
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            method="GET",
            path="/api/clinical/forms/?patient_name=Secret&ssn=123",
            status_code=200,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        log = UserActivityLog.objects.get()
        self.assertEqual(log.path, "/api/clinical/forms/")
