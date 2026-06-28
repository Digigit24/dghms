"""API tests for all 8 clinical ViewSets.

Covers for every ViewSet:
- Unauthenticated → 401
- Tenant A cannot read Tenant B data → 404
- Authenticated own-tenant → 200
"""

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
    ClinicalPicklistItem,
    ClinicalRecord,
    SavedFormSnapshot,
    UserFormPreference,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SYSTEM_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _make_token(tenant_id, user_id, permissions=None):
    """Build a valid Bearer JWT for the middleware."""
    payload = {
        "user_id": str(user_id),
        "email": f"{user_id}@test.com",
        "tenant_id": str(tenant_id),
        "tenant_slug": "test",
        "is_super_admin": False,
        "permissions": permissions or {"hms.clinical.view": "all", "hms.clinical.create": True, "hms.clinical.edit": True},
        "enabled_modules": ["hms"],
        "user_type": "staff",
        "is_patient": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class BaseViewSetTest(APITestCase):
    """Common fixtures shared by all ViewSet test cases."""

    def setUp(self):
        self.tenant_a = uuid.uuid4()
        self.tenant_b = uuid.uuid4()
        self.user_a = uuid.uuid4()
        self.user_b = uuid.uuid4()

        # System form (visible to all tenants)
        self.system_form = ClinicalForm.objects.get_or_create(
            tenant_id=_SYSTEM_TENANT,
            code="test_system_form",
            defaults={
                "name": "Test System Form",
                "status": ClinicalForm.Status.PUBLISHED,
                "is_system": True,
            },
        )[0]

        # Tenant A form
        self.form_a = ClinicalForm.objects.create(
            tenant_id=self.tenant_a,
            code=f"form_a_{uuid.uuid4().hex[:8]}",
            name="Form A",
            status=ClinicalForm.Status.PUBLISHED,
        )

        # Tenant B form
        self.form_b = ClinicalForm.objects.create(
            tenant_id=self.tenant_b,
            code=f"form_b_{uuid.uuid4().hex[:8]}",
            name="Form B",
            status=ClinicalForm.Status.PUBLISHED,
        )

        self.token_a = _make_token(self.tenant_a, self.user_a)
        self.token_b = _make_token(self.tenant_b, self.user_b)

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def deauth(self):
        self.client.credentials()


# ---------------------------------------------------------------------------
# 1. ClinicalFormViewSet
# ---------------------------------------------------------------------------

class ClinicalFormViewSetTest(BaseViewSetTest):
    """Tests for ClinicalFormViewSet."""

    def test_list_unauthenticated_returns_401(self):
        self.deauth()
        r = self.client.get(reverse("clinicalform-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_own_tenant_returns_200(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalform-list"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_list_excludes_other_tenant_forms(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalform-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.form_a.id, ids)
        self.assertNotIn(self.form_b.id, ids)

    def test_retrieve_wrong_tenant_returns_404(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalform-detail", kwargs={"pk": self.form_b.pk}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_own_tenant_returns_200(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalform-detail", kwargs={"pk": self.form_a.pk}))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_system_forms_visible_to_all_tenants(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalform-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.system_form.id, ids)


# ---------------------------------------------------------------------------
# 2. ClinicalFormSectionViewSet
# ---------------------------------------------------------------------------

class ClinicalFormSectionViewSetTest(BaseViewSetTest):
    """Tests for ClinicalFormSectionViewSet."""

    def setUp(self):
        super().setUp()
        self.section_a = ClinicalFormSection.objects.create(
            tenant_id=self.tenant_a,
            form=self.form_a,
            code="sec_a",
            title="Section A",
        )
        self.section_b = ClinicalFormSection.objects.create(
            tenant_id=self.tenant_b,
            form=self.form_b,
            code="sec_b",
            title="Section B",
        )

    def test_list_unauthenticated_returns_401(self):
        self.deauth()
        r = self.client.get(reverse("clinicalformsection-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_own_tenant_returns_200(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalformsection-list"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_list_excludes_other_tenant_sections(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalformsection-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.section_a.id, ids)
        self.assertNotIn(self.section_b.id, ids)

    def test_retrieve_wrong_tenant_returns_404(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalformsection-detail", kwargs={"pk": self.section_b.pk}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_own_returns_200(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalformsection-detail", kwargs={"pk": self.section_a.pk}))
        self.assertEqual(r.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 3. ClinicalFormFieldViewSet
# ---------------------------------------------------------------------------

class ClinicalFormFieldViewSetTest(BaseViewSetTest):
    """Tests for ClinicalFormFieldViewSet."""

    def setUp(self):
        super().setUp()
        sec_a = ClinicalFormSection.objects.create(
            tenant_id=self.tenant_a, form=self.form_a, code="s1", title="S1"
        )
        sec_b = ClinicalFormSection.objects.create(
            tenant_id=self.tenant_b, form=self.form_b, code="s2", title="S2"
        )
        self.field_a = ClinicalFormField.objects.create(
            tenant_id=self.tenant_a, section=sec_a, field_key="fk_a", label="Field A"
        )
        self.field_b = ClinicalFormField.objects.create(
            tenant_id=self.tenant_b, section=sec_b, field_key="fk_b", label="Field B"
        )

    def test_list_unauthenticated_returns_401(self):
        self.deauth()
        r = self.client.get(reverse("clinicalformfield-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_excludes_other_tenant_fields(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalformfield-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.field_a.id, ids)
        self.assertNotIn(self.field_b.id, ids)

    def test_retrieve_wrong_tenant_returns_404(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalformfield-detail", kwargs={"pk": self.field_b.pk}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# 4. ClinicalPicklistViewSet
# ---------------------------------------------------------------------------

class ClinicalPicklistViewSetTest(BaseViewSetTest):
    """Tests for ClinicalPicklistViewSet."""

    def setUp(self):
        super().setUp()
        self.pl_a = ClinicalPicklist.objects.create(
            tenant_id=self.tenant_a, code=f"pl_a_{uuid.uuid4().hex[:6]}", name="PL A"
        )
        self.pl_b = ClinicalPicklist.objects.create(
            tenant_id=self.tenant_b, code=f"pl_b_{uuid.uuid4().hex[:6]}", name="PL B"
        )

    def test_list_unauthenticated_returns_401(self):
        self.deauth()
        r = self.client.get(reverse("clinicalpicklist-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_excludes_other_tenant_picklists(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalpicklist-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.pl_a.id, ids)
        self.assertNotIn(self.pl_b.id, ids)

    def test_retrieve_wrong_tenant_returns_404(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalpicklist-detail", kwargs={"pk": self.pl_b.pk}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# 5. ClinicalPicklistItemViewSet
# ---------------------------------------------------------------------------

class ClinicalPicklistItemViewSetTest(BaseViewSetTest):
    """Tests for ClinicalPicklistItemViewSet."""

    def setUp(self):
        super().setUp()
        pl_a = ClinicalPicklist.objects.create(
            tenant_id=self.tenant_a, code=f"pla_{uuid.uuid4().hex[:6]}", name="PLA"
        )
        pl_b = ClinicalPicklist.objects.create(
            tenant_id=self.tenant_b, code=f"plb_{uuid.uuid4().hex[:6]}", name="PLB"
        )
        self.item_a = ClinicalPicklistItem.objects.create(
            tenant_id=self.tenant_a, picklist=pl_a, label="Item A", value="item_a"
        )
        self.item_b = ClinicalPicklistItem.objects.create(
            tenant_id=self.tenant_b, picklist=pl_b, label="Item B", value="item_b"
        )

    def test_list_unauthenticated_returns_401(self):
        self.deauth()
        r = self.client.get(reverse("clinicalpicklistitem-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_excludes_other_tenant_items(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalpicklistitem-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.item_a.id, ids)
        self.assertNotIn(self.item_b.id, ids)

    def test_retrieve_wrong_tenant_returns_404(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalpicklistitem-detail", kwargs={"pk": self.item_b.pk}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# 6. ClinicalRecordViewSet
# ---------------------------------------------------------------------------

class ClinicalRecordViewSetTest(BaseViewSetTest):
    """Tests for ClinicalRecordViewSet."""

    def setUp(self):
        super().setUp()
        self.record_a = ClinicalRecord.objects.create(
            tenant_id=self.tenant_a,
            form=self.form_a,
            encounter_type="opd_visit",
            encounter_id=1001,
        )
        self.record_b = ClinicalRecord.objects.create(
            tenant_id=self.tenant_b,
            form=self.form_b,
            encounter_type="opd_visit",
            encounter_id=2001,
        )

    def test_list_unauthenticated_returns_401(self):
        self.deauth()
        r = self.client.get(reverse("clinicalrecord-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_own_tenant_returns_200(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalrecord-list"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_list_excludes_other_tenant_records(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalrecord-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.record_a.id, ids)
        self.assertNotIn(self.record_b.id, ids)

    def test_retrieve_wrong_tenant_returns_404(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalrecord-detail", kwargs={"pk": self.record_b.pk}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_own_returns_200(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("clinicalrecord-detail", kwargs={"pk": self.record_a.pk}))
        self.assertEqual(r.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 7. UserFormPreferenceViewSet
# ---------------------------------------------------------------------------

class UserFormPreferenceViewSetTest(BaseViewSetTest):
    """Tests for UserFormPreferenceViewSet."""

    def setUp(self):
        super().setUp()
        self.pref_a = UserFormPreference.objects.create(
            tenant_id=self.tenant_a,
            user_id=self.user_a,
            form=self.form_a,
        )
        self.pref_b = UserFormPreference.objects.create(
            tenant_id=self.tenant_b,
            user_id=self.user_b,
            form=self.form_b,
        )

    def test_list_unauthenticated_returns_401(self):
        self.deauth()
        r = self.client.get(reverse("userformpreference-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_excludes_other_tenant_prefs(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("userformpreference-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.pref_a.id, ids)
        self.assertNotIn(self.pref_b.id, ids)

    def test_retrieve_wrong_tenant_returns_404(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("userformpreference-detail", kwargs={"pk": self.pref_b.pk}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_sets_user_id_from_jwt_not_body(self):
        """user_id must come from JWT, not the request body."""
        self.auth(self.token_a)
        evil_user_id = uuid.uuid4()
        r = self.client.post(
            reverse("userformpreference-list"),
            {"form": self.form_a.pk, "user_id": str(evil_user_id)},
            format="json",
        )
        if r.status_code == status.HTTP_201_CREATED:
            # user_id must be from JWT (user_a), not the submitted evil_user_id
            self.assertNotEqual(str(r.data.get("user_id")), str(evil_user_id))


# ---------------------------------------------------------------------------
# 8. SavedFormSnapshotViewSet
# ---------------------------------------------------------------------------

class SavedFormSnapshotViewSetTest(BaseViewSetTest):
    """Tests for SavedFormSnapshotViewSet."""

    def setUp(self):
        super().setUp()
        record_a = ClinicalRecord.objects.create(
            tenant_id=self.tenant_a, form=self.form_a,
            encounter_type="opd_visit", encounter_id=3001,
        )
        record_b = ClinicalRecord.objects.create(
            tenant_id=self.tenant_b, form=self.form_b,
            encounter_type="opd_visit", encounter_id=4001,
        )
        self.snap_a = SavedFormSnapshot.objects.create(
            tenant_id=self.tenant_a, record=record_a, name="Snap A", snapshot_data={}
        )
        self.snap_b = SavedFormSnapshot.objects.create(
            tenant_id=self.tenant_b, record=record_b, name="Snap B", snapshot_data={}
        )

    def test_list_unauthenticated_returns_401(self):
        self.deauth()
        r = self.client.get(reverse("savedformsnapshot-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_excludes_other_tenant_snapshots(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("savedformsnapshot-list"))
        ids = {item["id"] for item in r.data.get("results", r.data)}
        self.assertIn(self.snap_a.id, ids)
        self.assertNotIn(self.snap_b.id, ids)

    def test_retrieve_wrong_tenant_returns_404(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("savedformsnapshot-detail", kwargs={"pk": self.snap_b.pk}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_own_returns_200(self):
        self.auth(self.token_a)
        r = self.client.get(reverse("savedformsnapshot-detail", kwargs={"pk": self.snap_a.pk}))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
