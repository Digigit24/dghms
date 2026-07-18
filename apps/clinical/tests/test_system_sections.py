import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.clinical.models import ClinicalForm, ClinicalFormSection, FormSectionPlacement


SYSTEM_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _make_token(tenant_id, user_id, *, is_super_admin=False, permissions=None):
    payload = {
        "user_id": str(user_id),
        "email": f"{user_id}@test.com",
        "tenant_id": str(tenant_id),
        "tenant_slug": "test",
        "is_super_admin": is_super_admin,
        "permissions": permissions or {"hms.clinical.view": "all", "hms.clinical.edit": True},
        "enabled_modules": ["hms"],
        "roles": [],
        "user_type": "staff",
        "is_patient": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class SystemSectionAccessTests(APITestCase):
    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.system_form = ClinicalForm.objects.create(
            tenant_id=SYSTEM_TENANT_ID,
            code="system_test_form",
            name="System Test Form",
            status=ClinicalForm.Status.PUBLISHED,
            is_system=True,
        )
        self.stale_system_section = ClinicalFormSection.objects.create(
            tenant_id=SYSTEM_TENANT_ID,
            code="system_test_stale_section",
            title="Stale System Section",
            is_system=False,
        )
        FormSectionPlacement.objects.create(
            tenant_id=SYSTEM_TENANT_ID,
            form=self.system_form,
            section=self.stale_system_section,
            display_order=1,
        )

    def auth(self):
        token = _make_token(self.tenant_id, self.user_id, is_super_admin=True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_system_form_section_is_visible_even_when_section_flag_is_stale(self):
        self.auth()

        response = self.client.get(
            reverse(
                "clinicalformsection-detail",
                kwargs={"pk": self.stale_system_section.pk},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_system_form_section_can_be_patched_even_when_section_flag_is_stale(self):
        self.auth()

        response = self.client.patch(
            reverse(
                "clinicalformsection-detail",
                kwargs={"pk": self.stale_system_section.pk},
            ),
            {"config": {"visible_to_pharmacy": True}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.stale_system_section.refresh_from_db()
        self.assertEqual(
            self.stale_system_section.config,
            {"visible_to_pharmacy": True},
        )
