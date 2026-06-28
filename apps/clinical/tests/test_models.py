"""Tests for clinical models."""

import uuid

from django.test import TestCase

from apps.clinical.models import (
    ClinicalForm,
    ClinicalFormSection,
    ClinicalFormField,
    ClinicalRecord,
    ClinicalFieldValue,
)


class ClinicalFormModelTest(TestCase):
    def test_create_form(self):
        tenant_id = uuid.uuid4()
        form = ClinicalForm.objects.create(
            tenant_id=tenant_id,
            code="vitals",
            name="Vitals",
            status=ClinicalForm.Status.PUBLISHED,
            created_by_user_id=uuid.uuid4(),
        )
        self.assertEqual(form.code, "vitals")
        self.assertEqual(form.tenant_id, tenant_id)


class ClinicalRecordModelTest(TestCase):
    def test_create_record(self):
        tenant_id = uuid.uuid4()
        form = ClinicalForm.objects.create(
            tenant_id=tenant_id,
            code="vitals",
            name="Vitals",
        )
        record = ClinicalRecord.objects.create(
            tenant_id=tenant_id,
            form=form,
            encounter_type="opd_visit",
            encounter_id=123,
            created_by_user_id=uuid.uuid4(),
        )
        self.assertEqual(record.encounter_type, "opd_visit")
        self.assertFalse(record.is_locked)


class ClinicalFieldValueModelTest(TestCase):
    def test_typed_value_columns(self):
        tenant_id = uuid.uuid4()
        form = ClinicalForm.objects.create(tenant_id=tenant_id, code="vitals", name="Vitals")
        section = ClinicalFormSection.objects.create(
            tenant_id=tenant_id, form=form, code="vitals", title="Vitals"
        )
        field = ClinicalFormField.objects.create(
            tenant_id=tenant_id,
            section=section,
            field_key="heart_rate",
            field_type=ClinicalFormField.FieldType.NUMBER,
            label="Heart Rate",
        )
        record = ClinicalRecord.objects.create(
            tenant_id=tenant_id,
            form=form,
            encounter_type="opd_visit",
            encounter_id=1,
        )
        value = ClinicalFieldValue.objects.create(
            tenant_id=tenant_id,
            record=record,
            field=field,
            value_number=72,
        )
        self.assertEqual(value.value_number, 72)
