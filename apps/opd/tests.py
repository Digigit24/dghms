
from decimal import Decimal
import datetime
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from django.conf import settings
from django.db.models.signals import post_save
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.doctors.models import DoctorProfile
from apps.opd.management.commands.recompute_opd_bill_totals import Command
from apps.opd.filters import VisitFilter
from apps.opd.models import OPDBillItem, Visit
from apps.patients.models import PatientProfile
from apps.opd.serializers import VisitListSerializer, VisitSetFollowUpSerializer
from apps.opd.signals import update_opd_bill_totals
from apps.opd.views import VisitViewSet, _invalidate_today_cache


def _jwt_for(*, tenant_id, user_id, email, permissions):
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {
            "user_id": str(user_id),
            "email": email,
            "tenant_id": str(tenant_id),
            "tenant_slug": "test-tenant",
            "is_super_admin": False,
            "permissions": permissions,
            "enabled_modules": ["hms"],
            "roles": [],
            "user_type": "staff",
            "iat": int(now.timestamp()),
            "exp": int((now + datetime.timedelta(minutes=10)).timestamp()),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


class OPDBillSynchronizationTests(SimpleTestCase):
    def test_bill_item_recalculation_receiver_is_registered(self):
        synchronous_receivers, _ = post_save._live_receivers(OPDBillItem)
        self.assertIn(update_opd_bill_totals, synchronous_receivers)

    def test_recompute_uses_items_and_payment_ledger(self):
        bill = SimpleNamespace(
            items_total=Decimal("1000.00"),
            ledger_received=Decimal("250.00"),
            discount_percent=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
        )

        self.assertEqual(
            Command._expected_values(bill),
            {
                "total_amount": Decimal("1000.00"),
                "discount_amount": Decimal("100.00"),
                "payable_amount": Decimal("900.00"),
                "received_amount": Decimal("250.00"),
                "balance_amount": Decimal("650.00"),
                "payment_status": "partial",
            },
        )


class VisitFollowUpContractTests(SimpleTestCase):
    def test_visit_list_exposes_flat_patient_fields(self):
        fields = VisitListSerializer().fields
        self.assertIn("patient_mobile", fields)
        self.assertIn("patient_age", fields)
        self.assertIn("patient_gender", fields)

    def test_follow_up_filters_match_frontend_contract(self):
        filters = VisitFilter.base_filters
        self.assertIn("follow_up_required", filters)
        self.assertIn("follow_up_date_from", filters)
        self.assertIn("follow_up_date_to", filters)
        self.assertEqual(filters["follow_up_date_from"].lookup_expr, "gte")
        self.assertEqual(filters["follow_up_date_to"].lookup_expr, "lte")

    def test_set_follow_up_payload_accepts_only_contract_fields(self):
        serializer = VisitSetFollowUpSerializer(data={
            "follow_up_required": True,
            "follow_up_date": "2026-07-25",
            "follow_up_notes": "Review in one week",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

        serializer = VisitSetFollowUpSerializer(data={
            "follow_up_required": True,
            "follow_up_date": "2026-07-25",
            "status": "completed",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("status", serializer.errors)

    def test_set_follow_up_uses_edit_permission(self):
        self.assertEqual(VisitViewSet.action_permission_map["set_follow_up"], "edit")


class VisitCacheFailureTests(SimpleTestCase):
    @patch("apps.opd.views.CeliyoCache")
    def test_cache_invalidation_is_best_effort(self, cache_class):
        cache_class.return_value.delete_pattern.side_effect = ConnectionError(
            "redis unavailable"
        )

        _invalidate_today_cache("tenant-1")


class VisitOwnScopeTests(TestCase):
    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.doctor_user_id = uuid.uuid4()
        self.other_user_id = uuid.uuid4()
        self.doctor = DoctorProfile.objects.create(
            tenant_id=self.tenant_id,
            user_id=self.doctor_user_id,
            first_name="Own",
            last_name="Doctor",
            status="active",
        )
        self.other_doctor = DoctorProfile.objects.create(
            tenant_id=self.tenant_id,
            user_id=self.other_user_id,
            first_name="Other",
            last_name="Doctor",
            status="active",
        )
        self.patient = PatientProfile.objects.create(
            tenant_id=self.tenant_id,
            first_name="Test",
            last_name="Patient",
            gender="male",
            mobile_primary="9999999999",
        )
        self.own_visit = Visit.objects.create(
            tenant_id=self.tenant_id,
            visit_number="OPD/OWN/001",
            patient=self.patient,
            doctor=self.doctor,
            status="waiting",
            visit_date=datetime.date.today(),
        )
        Visit.objects.create(
            tenant_id=self.tenant_id,
            visit_number="OPD/OTHER/001",
            patient=self.patient,
            doctor=self.other_doctor,
            status="waiting",
            visit_date=datetime.date.today(),
        )

    def test_queue_doctor_me_resolves_profile_with_own_view_scope(self):
        client = APIClient()
        token = _jwt_for(
            tenant_id=self.tenant_id,
            user_id=self.doctor_user_id,
            email="doctor@example.com",
            permissions={"hms.opd.view": "own"},
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = client.get("/api/opd/visits/queue/?doctor=me")

        self.assertEqual(response.status_code, 200)
        waiting_ids = [row["id"] for row in response.data["data"]["waiting"]]
        self.assertEqual(waiting_ids, [self.own_visit.id])
