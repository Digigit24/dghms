"""Focused tests for clinical runtime endpoints used by the frontend renderer."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.clinical.models import (
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormSection,
    ClinicalPicklist,
    ClinicalRecord,
    FormSectionPlacement,
)


def make_token(tenant_id, user_id):
    payload = {
        "user_id": str(user_id),
        "email": f"{user_id}@test.com",
        "tenant_id": str(tenant_id),
        "tenant_slug": "test",
        "is_super_admin": False,
        "permissions": {
            "hms.clinical.view": "all",
            "hms.clinical.create": True,
            "hms.clinical.edit": True,
        },
        "enabled_modules": ["hms"],
        "user_type": "staff",
        "is_patient": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class ClinicalRuntimeEndpointTests(APITestCase):
    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        token = make_token(self.tenant_id, self.user_id)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_picklists_can_filter_by_code(self):
        match = ClinicalPicklist.objects.create(
            tenant_id=self.tenant_id,
            code="chief_complaints",
            name="Chief Complaints",
        )
        ClinicalPicklist.objects.create(
            tenant_id=self.tenant_id,
            code="past_history",
            name="Past History",
        )

        response = self.client.get(reverse("clinicalpicklist-list"), {"code": "chief_complaints"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data.get("results", response.data)
        self.assertEqual([row["id"] for row in rows], [match.id])

    def test_pull_returns_latest_record_values_for_requested_fields(self):
        form = ClinicalForm.objects.create(
            tenant_id=self.tenant_id,
            code="round_note",
            name="Round Note",
            status=ClinicalForm.Status.PUBLISHED,
        )
        section = ClinicalFormSection.objects.create(
            tenant_id=self.tenant_id,
            code="round_note_main",
            title="Round Note",
        )
        FormSectionPlacement.objects.create(
            tenant_id=self.tenant_id,
            form=form,
            section=section,
            display_order=1,
        )
        note_field = ClinicalFormField.objects.create(
            tenant_id=self.tenant_id,
            section=section,
            field_key="clinical_note",
            field_type=ClinicalFormField.FieldType.TEXTAREA,
            label="Clinical Note",
        )
        temp_field = ClinicalFormField.objects.create(
            tenant_id=self.tenant_id,
            section=section,
            field_key="temperature",
            field_type=ClinicalFormField.FieldType.NUMBER,
            label="Temperature",
            display_order=2,
        )
        old_record = ClinicalRecord.objects.create(
            tenant_id=self.tenant_id,
            form=form,
            encounter_type="ipd_admission",
            encounter_id=100,
            status=ClinicalRecord.Status.COMPLETED,
        )
        ClinicalFieldValue.objects.create(
            tenant_id=self.tenant_id,
            record=old_record,
            field=note_field,
            value_text="old note",
        )
        latest_record = ClinicalRecord.objects.create(
            tenant_id=self.tenant_id,
            form=form,
            encounter_type="ipd_admission",
            encounter_id=101,
            status=ClinicalRecord.Status.IN_PROGRESS,
        )
        ClinicalFieldValue.objects.create(
            tenant_id=self.tenant_id,
            record=latest_record,
            field=note_field,
            value_text="patient improving",
        )
        ClinicalFieldValue.objects.create(
            tenant_id=self.tenant_id,
            record=latest_record,
            field=temp_field,
            value_number="98.600000",
        )

        response = self.client.get(
            reverse(
                "clinical-encounter-pull",
                kwargs={"encounter_type": "ipd_admission", "encounter_id": 101},
            ),
            {"source_form": "round_note", "fields": "clinical_note,temperature,missing"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["clinical_note"], "patient improving")
        self.assertEqual(response.data["data"]["temperature"], 98.6)
        self.assertIsNone(response.data["data"]["missing"])

