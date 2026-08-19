import datetime
import threading
import uuid
from decimal import Decimal

import jwt
from django.conf import settings
from django.db import connections, transaction
from django.db.models import Model as DjangoModel
from django.db.models.signals import post_save
from django.test import SimpleTestCase
from django.test import TestCase
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from apps.doctors.models import DoctorProfile
from apps.hospital.models import Hospital
from apps.ipd.models import Admission, Bed, IPDBilling, IPDBillingSequence, IPDBillItem, Ward
from apps.ipd.signals import update_ipd_bill_totals
from apps.ipd.serializers import BedListSerializer, BedSerializer
from apps.patients.models import PatientProfile
from apps.payments.models import BillPayment


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


class BedMasterContractTests(SimpleTestCase):
    def test_list_response_contains_editable_feature_fields(self):
        fields = set(BedListSerializer().fields)
        self.assertTrue({
            "has_oxygen", "has_ventilator", "description", "is_active"
        }.issubset(fields))

    def test_unoccupied_bed_cannot_be_manually_marked_occupied(self):
        serializer = BedSerializer()
        serializer.instance = None
        with self.assertRaisesMessage(ValidationError, "admission or bed transfer"):
            serializer.validate({"status": "occupied"})


class AdmissionOwnScopeTests(TestCase):
    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.doctor_user_id = uuid.uuid4()
        self.other_user_id = uuid.uuid4()
        DoctorProfile.objects.create(
            tenant_id=self.tenant_id,
            user_id=self.doctor_user_id,
            first_name="Own",
            last_name="Doctor",
            status="active",
        )
        DoctorProfile.objects.create(
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
        self.ward = Ward.objects.create(
            tenant_id=self.tenant_id,
            name="Ward A",
            type="general",
            floor="1",
        )
        self.bed = Bed.objects.create(
            tenant_id=self.tenant_id,
            ward=self.ward,
            bed_number="A-1",
        )
        self.own_admission = Admission.objects.create(
            tenant_id=self.tenant_id,
            admission_id="IPD/OWN/001",
            patient=self.patient,
            doctor_id=self.doctor_user_id,
            ward=self.ward,
            bed=self.bed,
            status="admitted",
            reason="Testing",
        )
        Admission.objects.create(
            tenant_id=self.tenant_id,
            admission_id="IPD/OTHER/001",
            patient=self.patient,
            doctor_id=self.other_user_id,
            ward=self.ward,
            status="admitted",
            reason="Testing",
        )

    def test_list_doctor_me_resolves_profile_with_own_view_scope(self):
        client = APIClient()
        token = _jwt_for(
            tenant_id=self.tenant_id,
            user_id=self.doctor_user_id,
            email="doctor@example.com",
            permissions={"hms.ipd.view": "own"},
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = client.get(
            "/api/ipd/admissions/?status=admitted&doctor=me&page_size=100"
        )

        self.assertEqual(response.status_code, 200)
        result_ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(result_ids, [self.own_admission.id])


class IPDBillSynchronizationTests(SimpleTestCase):
    def test_bill_item_recalculation_receiver_is_registered(self):
        synchronous_receivers, _ = post_save._live_receivers(IPDBillItem)
        self.assertIn(update_ipd_bill_totals, synchronous_receivers)


def _super_admin_jwt(*, tenant_id, user_id=None, email="admin@example.com"):
    """JWT with is_super_admin=True — bypasses HMSPermission entirely, so
    these tests exercise the billing-mode/advance-payment business logic
    without needing to hand-construct a full hms.ipd.* permission grant.
    """
    user_id = user_id or uuid.uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {
            "user_id": str(user_id),
            "email": email,
            "tenant_id": str(tenant_id),
            "tenant_slug": "test-tenant",
            "is_super_admin": True,
            "permissions": {},
            "enabled_modules": ["hms"],
            "roles": [],
            "user_type": "staff",
            "iat": int(now.timestamp()),
            "exp": int((now + datetime.timedelta(minutes=10)).timestamp()),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


class IPDBillingModesAdvanceTestBase(TestCase):
    """Shared fixture: one tenant, one hospital (mode configurable), one
    bed-less admission, and an authenticated super-admin APIClient.
    """

    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

        self.hospital = Hospital(
            tenant_id=self.tenant_id,
            name="Test Hospital",
            email="hospital@example.com",
            phone="1234567890",
            address="Addr",
            city="City",
            state="State",
            pincode="123456",
        )
        # Bypass Hospital.save()'s singleton guard, same as
        # apps.hospital.views._get_or_create_hospital does for tests/fixtures.
        DjangoModel.save(self.hospital)

        self.patient = PatientProfile.objects.create(
            tenant_id=self.tenant_id,
            first_name="Advance",
            last_name="Patient",
            gender="male",
            mobile_primary="9000000001",
        )
        self.ward = Ward.objects.create(
            tenant_id=self.tenant_id, name="General", type="general", floor="1"
        )
        self.admission = Admission.objects.create(
            tenant_id=self.tenant_id,
            admission_id="IPD/ADV/001",
            patient=self.patient,
            doctor_id=uuid.uuid4(),
            ward=self.ward,
            status="admitted",
            reason="Testing advance payments",
        )

        self.client = APIClient()
        token = _super_admin_jwt(tenant_id=self.tenant_id, user_id=self.user_id)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def set_mode(self, mode):
        self.hospital.ipd_billing_mode = mode
        self.hospital.save(update_fields=["ipd_billing_mode"])

    def create_bill(self):
        resp = self.client.post(
            "/api/ipd/billings/", {"admission": self.admission.id}, format="json"
        )
        assert resp.status_code == 201, resp.data
        return resp.data["id"]

    def add_item(self, bill_id, unit_price):
        resp = self.client.post(
            "/api/ipd/bill-items/",
            {
                "bill": bill_id,
                "item_name": "Charge",
                "source": "Other",
                "quantity": 1,
                "unit_price": str(unit_price),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        return resp.data["id"]


class IPDBillingModeGuardTests(IPDBillingModesAdvanceTestBase):
    """H) 409 guard on IPDBillingViewSet.create(), both modes."""

    def test_single_accumulated_mode_blocks_second_regular_bill(self):
        self.set_mode("single_accumulated")

        resp1 = self.client.post(
            "/api/ipd/billings/", {"admission": self.admission.id}, format="json"
        )
        self.assertEqual(resp1.status_code, 201, resp1.data)

        resp2 = self.client.post(
            "/api/ipd/billings/", {"admission": self.admission.id}, format="json"
        )
        self.assertEqual(resp2.status_code, 409, resp2.data)
        self.assertFalse(resp2.data["success"])
        self.assertEqual(resp2.data["error_code"], "IPD_BILL_ALREADY_EXISTS")

    def test_single_accumulated_mode_exempts_mediclaim_bills(self):
        self.set_mode("single_accumulated")
        self.create_bill()

        self.admission.has_mediclaim = True
        self.admission.tpa_name = "Star Health"
        self.admission.save(update_fields=["has_mediclaim", "tpa_name"])

        resp = self.client.post(
            "/api/ipd/billings/mediclaim/",
            {"admission": self.admission.id, "total_amount": "1000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_multiple_mode_allows_unlimited_regular_bills(self):
        self.set_mode("multiple")

        resp1 = self.client.post(
            "/api/ipd/billings/", {"admission": self.admission.id}, format="json"
        )
        self.assertEqual(resp1.status_code, 201, resp1.data)

        resp2 = self.client.post(
            "/api/ipd/billings/", {"admission": self.admission.id}, format="json"
        )
        self.assertEqual(resp2.status_code, 201, resp2.data)


class AdvancePaymentTests(IPDBillingModesAdvanceTestBase):
    """E/F) record_advance + apply_advance happy path and balance math."""

    def test_record_advance_rejected_for_discharged_admission(self):
        self.admission.status = "discharged"
        self.admission.save(update_fields=["status"])

        resp = self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/record_advance/",
            {"amount": "500.00", "payment_mode": "cash"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error_code"], "ADMISSION_DISCHARGED")

    def test_record_advance_creates_ledger_rows_and_updates_capabilities(self):
        resp = self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/record_advance/",
            {"amount": "1000.00", "payment_mode": "cash", "notes": "Deposit"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data["success"])
        self.assertIn("payment_group_id", resp.data)
        self.assertEqual(len(resp.data["receipt_numbers"]), 1)

        caps = resp.data["data"]["billing_capabilities"]
        self.assertEqual(caps["total_advance_paid"], "1000.00")
        self.assertEqual(caps["advance_applied"], "0.00")
        self.assertEqual(caps["advance_balance"], "1000.00")

        ledger_row = BillPayment.objects.get(admission=self.admission, bill_type="advance")
        self.assertEqual(ledger_row.amount, Decimal("1000.00"))
        self.assertEqual(ledger_row.applied_amount, Decimal("0.00"))
        self.assertIsNone(ledger_row.ipd_bill_id)

    def test_apply_advance_partial_then_remaining_and_balance_math(self):
        self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/record_advance/",
            {"amount": "1000.00", "payment_mode": "cash"},
            format="json",
        )
        bill_id = self.create_bill()
        self.add_item(bill_id, "600.00")

        # Partial apply.
        resp = self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/apply_advance/",
            {"bill_id": bill_id, "amount": "400.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        bill_data = resp.data["data"]["bill"]
        self.assertEqual(bill_data["received_amount"], "400.00")
        self.assertEqual(bill_data["payment_status"], "partial")

        caps = resp.data["data"]["billing_capabilities"]
        self.assertEqual(caps["advance_applied"], "400.00")
        self.assertEqual(caps["advance_balance"], "600.00")
        self.assertEqual(
            Decimal(caps["total_advance_paid"]) - Decimal(caps["advance_applied"]),
            Decimal(caps["advance_balance"]),
        )

        # Apply remaining (amount omitted) — capped at the bill's own
        # remaining balance (600.00 payable - 400.00 received = 200.00),
        # even though 600.00 of advance is still unapplied.
        resp2 = self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/apply_advance/",
            {"bill_id": bill_id},
            format="json",
        )
        self.assertEqual(resp2.status_code, 200, resp2.data)
        bill_data2 = resp2.data["data"]["bill"]
        self.assertEqual(bill_data2["received_amount"], "600.00")
        self.assertEqual(bill_data2["payment_status"], "paid")

        caps2 = resp2.data["data"]["billing_capabilities"]
        self.assertEqual(caps2["advance_applied"], "600.00")
        self.assertEqual(caps2["advance_balance"], "400.00")
        self.assertEqual(
            Decimal(caps2["total_advance_paid"]) - Decimal(caps2["advance_applied"]),
            Decimal(caps2["advance_balance"]),
        )

        self.admission.refresh_from_db()
        self.assertEqual(self.admission.total_charges, Decimal("600.00"))
        # total_received = Σ bill.received_amount only — apply_advance already
        # wrote the applied advance onto the bill's own received_amount, so
        # adding advance_applied on top here would double-count it. The bill
        # is fully paid (600.00 payable, 600.00 received via advance), so the
        # admission is fully settled too.
        self.assertEqual(self.admission.total_received, Decimal("600.00"))
        self.assertEqual(self.admission.balance_due, Decimal("0.00"))
        self.assertEqual(
            self.admission.balance_due, self.admission.total_charges - self.admission.total_received
        )

    def test_apply_advance_amount_exceeding_balance_is_rejected(self):
        self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/record_advance/",
            {"amount": "100.00", "payment_mode": "cash"},
            format="json",
        )
        bill_id = self.create_bill()
        self.add_item(bill_id, "600.00")

        resp = self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/apply_advance/",
            {"bill_id": bill_id, "amount": "500.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error_code"], "ADVANCE_EXCEEDS_BALANCE")

    def test_apply_advance_rejects_bill_from_another_admission(self):
        self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/record_advance/",
            {"amount": "1000.00", "payment_mode": "cash"},
            format="json",
        )
        other_admission = Admission.objects.create(
            tenant_id=self.tenant_id,
            admission_id="IPD/ADV/002",
            patient=self.patient,
            doctor_id=uuid.uuid4(),
            ward=self.ward,
            status="admitted",
            reason="Other admission",
        )
        other_bill = IPDBilling.objects.create(
            tenant_id=self.tenant_id, admission=other_admission,
        )
        IPDBillItem.objects.create(
            tenant_id=self.tenant_id, bill=other_bill, item_name="X", source="Other",
            quantity=1, system_calculated_price=Decimal("300.00"), unit_price=Decimal("300.00"),
            total_price=Decimal("300.00"),
        )

        resp = self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/apply_advance/",
            {"bill_id": other_bill.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data["error_code"], "BILL_NOT_FOUND")


class RollupSyncTests(IPDBillingModesAdvanceTestBase):
    """C) Admission rollup fields stay in sync across multiple bills, direct
    payments, and advances on one admission.
    """

    def test_rollup_fields_track_multiple_bills_payments_and_advances(self):
        self.set_mode("multiple")

        bill1 = self.create_bill()
        self.add_item(bill1, "1000.00")
        bill2 = self.create_bill()
        self.add_item(bill2, "500.00")

        self.admission.refresh_from_db()
        self.assertEqual(self.admission.total_charges, Decimal("1500.00"))
        self.assertEqual(self.admission.total_received, Decimal("0.00"))
        self.assertEqual(self.admission.balance_due, Decimal("1500.00"))

        # Direct payment on bill1 via add_payment.
        resp = self.client.post(
            f"/api/ipd/billings/{bill1}/add_payment/",
            {"amount": "1000.00", "payment_mode": "cash"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)

        self.admission.refresh_from_db()
        self.assertEqual(self.admission.total_received, Decimal("1000.00"))
        self.assertEqual(self.admission.balance_due, Decimal("500.00"))

        # Record an advance — total_advance_paid/advance_balance move, but
        # total_received/balance_due are untouched until it's applied.
        self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/record_advance/",
            {"amount": "500.00", "payment_mode": "cash"},
            format="json",
        )
        self.admission.refresh_from_db()
        self.assertEqual(self.admission.total_advance_paid, Decimal("500.00"))
        self.assertEqual(self.admission.advance_balance, Decimal("500.00"))
        self.assertEqual(self.admission.total_received, Decimal("1000.00"))
        self.assertEqual(self.admission.balance_due, Decimal("500.00"))

        # Apply the full advance to bill2.
        self.client.post(
            f"/api/ipd/admissions/{self.admission.id}/apply_advance/",
            {"bill_id": bill2},
            format="json",
        )
        self.admission.refresh_from_db()
        self.assertEqual(self.admission.advance_applied, Decimal("500.00"))
        self.assertEqual(self.admission.advance_balance, Decimal("0.00"))
        self.assertEqual(
            self.admission.total_advance_paid - self.admission.advance_applied,
            self.admission.advance_balance,
        )

        bill2_obj = IPDBilling.objects.get(pk=bill2)
        self.assertEqual(bill2_obj.received_amount, Decimal("500.00"))
        self.assertEqual(bill2_obj.payment_status, "paid")

        # total_received = Σ bill.received_amount (1000 direct on bill1 +
        # 500 advance-applied on bill2) — NOT + advance_applied again, since
        # that 500 is already inside bill2.received_amount above.
        self.assertEqual(self.admission.total_received, Decimal("1500.00"))
        self.assertEqual(self.admission.balance_due, Decimal("0.00"))

        # Deleting a bill item recomputes total_charges/total_received too.
        item_id = self.add_item(bill1, "200.00")
        self.admission.refresh_from_db()
        self.assertEqual(self.admission.total_charges, Decimal("1700.00"))

        self.client.delete(f"/api/ipd/bill-items/{item_id}/")
        self.admission.refresh_from_db()
        self.assertEqual(self.admission.total_charges, Decimal("1500.00"))

    def test_mediclaim_bills_excluded_from_charges_and_received(self):
        self.admission.has_mediclaim = True
        self.admission.tpa_name = "Star Health"
        self.admission.save(update_fields=["has_mediclaim", "tpa_name"])

        resp = self.client.post(
            "/api/ipd/billings/mediclaim/",
            {"admission": self.admission.id, "total_amount": "50000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)

        self.admission.refresh_from_db()
        self.assertEqual(self.admission.total_charges, Decimal("0.00"))
        self.assertEqual(self.admission.total_received, Decimal("0.00"))


class PaidLockItemTests(IPDBillingModesAdvanceTestBase):
    """I.5) Per-item paid-lock: items existing before the bill's last paid
    transition are locked; items added after it stay editable.
    """

    def test_old_items_locked_new_items_addable_after_paid(self):
        bill_id = self.create_bill()
        old_item_id = self.add_item(bill_id, "500.00")

        pay_resp = self.client.post(
            f"/api/ipd/billings/{bill_id}/add_payment/",
            {"amount": "500.00", "payment_mode": "cash"},
            format="json",
        )
        self.assertEqual(pay_resp.status_code, 200, pay_resp.data)
        bill = IPDBilling.objects.get(pk=bill_id)
        self.assertEqual(bill.payment_status, "paid")
        self.assertIsNotNone(bill.paid_transition_at)

        # The pre-existing item is now locked.
        update_resp = self.client.patch(
            f"/api/ipd/bill-items/{old_item_id}/", {"unit_price": "550.00"}, format="json"
        )
        self.assertEqual(update_resp.status_code, 422)
        self.assertEqual(update_resp.data["error"]["code"], "BILL_LOCKED")

        delete_resp = self.client.delete(f"/api/ipd/bill-items/{old_item_id}/")
        self.assertEqual(delete_resp.status_code, 422)

        # A brand-new item can still be added to this already-paid bill —
        # this is the whole point of the fix (single_accumulated mode keeps
        # billing into the one accumulated bill after it reaches 'paid').
        new_item_id = self.add_item(bill_id, "300.00")
        bill.refresh_from_db()
        self.assertEqual(bill.payable_amount, Decimal("800.00"))
        # received (500) < payable (800) now, so the bill fell back to partial.
        self.assertEqual(bill.payment_status, "partial")

        # The new item is NOT locked (bill isn't 'paid' right now anyway).
        update_new_resp = self.client.patch(
            f"/api/ipd/bill-items/{new_item_id}/", {"unit_price": "350.00"}, format="json"
        )
        self.assertEqual(update_new_resp.status_code, 200, update_new_resp.data)

        # Bring the bill back to 'paid' — a second, later transition.
        pay_resp2 = self.client.post(
            f"/api/ipd/billings/{bill_id}/add_payment/",
            {"amount": "350.00", "payment_mode": "cash"},
            format="json",
        )
        self.assertEqual(pay_resp2.status_code, 200, pay_resp2.data)
        bill.refresh_from_db()
        self.assertEqual(bill.payment_status, "paid")

        # Now the item added between the two transitions is ALSO locked,
        # since it existed before the bill's most recent paid transition.
        update_new_resp2 = self.client.patch(
            f"/api/ipd/bill-items/{new_item_id}/", {"unit_price": "360.00"}, format="json"
        )
        self.assertEqual(update_new_resp2.status_code, 422)

        # But a third item, created after this second transition, is still addable.
        third_item_id = self.add_item(bill_id, "100.00")
        self.assertIsNotNone(third_item_id)


class IPDBillingSequenceConcurrencyTests(TransactionTestCase):
    """I.1) Per-tenant-per-day bill-number sequence stays collision-free
    under concurrent creation — mirrors the intent of OPDBillSequence's
    locking behavior (no direct OPDBillSequence-specific test exists to
    mirror verbatim).
    """

    def test_concurrent_bill_number_generation_never_collides(self):
        tenant_id = uuid.uuid4()
        today = datetime.date.today()
        thread_count = 5
        results = []
        errors = []
        lock = threading.Lock()

        def worker():
            try:
                # next_bill_number() requires an enclosing atomic block (its
                # select_for_update() would otherwise raise
                # TransactionManagementError) — IPDBilling.save() normally
                # provides one; here we provide it directly since each
                # thread calls the sequence in isolation.
                with transaction.atomic():
                    number = IPDBillingSequence.next_bill_number(tenant_id, today, "IPD-BILL")
                with lock:
                    results.append(number)
            except Exception as exc:  # pragma: no cover - failure path
                with lock:
                    errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), thread_count)
        self.assertEqual(len(set(results)), thread_count, results)

    def test_bill_number_uniqueness_is_scoped_per_tenant_not_global(self):
        """Two tenants can independently own IPD-BILL/<today>/001 — bill_number
        is unique_together(tenant_id, bill_number), not globally unique.
        """
        patient_tenant_a = uuid.uuid4()
        patient_tenant_b = uuid.uuid4()

        def make_admission(tenant_id, suffix):
            patient = PatientProfile.objects.create(
                tenant_id=tenant_id, first_name="P", last_name=suffix,
                gender="male", mobile_primary=f"90000000{suffix}",
            )
            ward = Ward.objects.create(tenant_id=tenant_id, name="W", type="general", floor="1")
            return Admission.objects.create(
                tenant_id=tenant_id, admission_id=f"IPD/{suffix}/001", patient=patient,
                doctor_id=uuid.uuid4(), ward=ward, status="admitted", reason="test",
            )

        admission_a = make_admission(patient_tenant_a, "A")
        admission_b = make_admission(patient_tenant_b, "B")

        bill_a = IPDBilling.objects.create(tenant_id=patient_tenant_a, admission=admission_a)
        bill_b = IPDBilling.objects.create(tenant_id=patient_tenant_b, admission=admission_b)

        self.assertEqual(bill_a.bill_number, bill_b.bill_number)
        self.assertNotEqual(bill_a.tenant_id, bill_b.tenant_id)


class ApplyAdvanceLostUpdateTests(TransactionTestCase):
    """Regression test: apply_advance_to_bill() now select_for_update()s the
    IPDBilling row before reading/writing received_amount, so two concurrent
    applications against the SAME bill can no longer lost-update each other
    (both threads reading the pre-update received_amount and each writing
    their own delta on top of it, with the loser's contribution silently
    discarded).
    """

    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.patient = PatientProfile.objects.create(
            tenant_id=self.tenant_id, first_name="Race", last_name="Patient",
            gender="male", mobile_primary="9000000099",
        )
        self.ward = Ward.objects.create(
            tenant_id=self.tenant_id, name="Ward", type="general", floor="1"
        )
        self.admission = Admission.objects.create(
            tenant_id=self.tenant_id, admission_id="IPD/RACE/001", patient=self.patient,
            doctor_id=uuid.uuid4(), ward=self.ward, status="admitted", reason="test",
        )
        self.bill = IPDBilling.objects.create(tenant_id=self.tenant_id, admission=self.admission)
        IPDBillItem.objects.create(
            tenant_id=self.tenant_id, bill=self.bill, item_name="Big charge", source="Other",
            quantity=1, system_calculated_price=Decimal("2000.00"), unit_price=Decimal("2000.00"),
            total_price=Decimal("2000.00"),
        )
        # Two separate deposits so each concurrent apply_advance call has its
        # own funds to draw from — isolates the bill-row race this test
        # targets from the (already-correct) advance-row FIFO consumption.
        BillPayment.objects.create(
            tenant_id=self.tenant_id, bill_type="advance", admission=self.admission,
            amount=Decimal("500.00"),
        )
        BillPayment.objects.create(
            tenant_id=self.tenant_id, bill_type="advance", admission=self.admission,
            amount=Decimal("500.00"),
        )

    def test_concurrent_apply_advance_calls_do_not_lose_updates(self):
        from apps.ipd.services.billing import apply_advance_to_bill

        errors = []
        lock = threading.Lock()

        def worker():
            try:
                # apply_advance_to_bill() opens its own transaction.atomic()
                # block internally (that's what select_for_update()s the
                # bill row) — no outer atomic needed here.
                admission = Admission.objects.get(pk=self.admission.pk)
                bill = IPDBilling.objects.get(pk=self.bill.pk)
                apply_advance_to_bill(admission, bill, Decimal("500.00"))
            except Exception as exc:  # pragma: no cover - failure path
                with lock:
                    errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        bill = IPDBilling.objects.get(pk=self.bill.pk)
        # Without the select_for_update() fix, one thread's +500 delta could
        # be silently overwritten by the other's stale read, leaving 500.00
        # instead of the correct sum of both applications.
        self.assertEqual(bill.received_amount, Decimal("1000.00"))
        self.assertEqual(bill.payment_status, "partial")

        admission = Admission.objects.get(pk=self.admission.pk)
        self.assertEqual(admission.advance_applied, Decimal("1000.00"))
        self.assertEqual(admission.advance_balance, Decimal("0.00"))
        self.assertEqual(admission.total_received, Decimal("1000.00"))
