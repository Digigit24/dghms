import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.doctors.models import DoctorProfile
from apps.ipd.models import Admission, Ward
from apps.patients.models import PatientProfile
from apps.payments.models import BillPayment


class BillPaymentAdvanceValidationTests(TestCase):
    """B) bill_type='advance' rows require admission set and ipd_bill null."""

    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.patient = PatientProfile.objects.create(
            tenant_id=self.tenant_id, first_name="A", last_name="B",
            gender="male", mobile_primary="9000000009",
        )
        self.ward = Ward.objects.create(
            tenant_id=self.tenant_id, name="Ward", type="general", floor="1"
        )
        self.admission = Admission.objects.create(
            tenant_id=self.tenant_id, admission_id="IPD/PAY/001", patient=self.patient,
            doctor_id=uuid.uuid4(), ward=self.ward, status="admitted", reason="test",
        )

    def test_advance_row_requires_admission(self):
        with self.assertRaises(ValidationError):
            BillPayment.objects.create(
                tenant_id=self.tenant_id, bill_type="advance", amount=Decimal("100.00"),
            )

    def test_advance_row_rejects_ipd_bill(self):
        from apps.ipd.models import IPDBilling

        bill = IPDBilling.objects.create(tenant_id=self.tenant_id, admission=self.admission)
        with self.assertRaises(ValidationError):
            BillPayment.objects.create(
                tenant_id=self.tenant_id, bill_type="advance", admission=self.admission,
                ipd_bill=bill, amount=Decimal("100.00"),
            )

    def test_valid_advance_row_saves(self):
        payment = BillPayment.objects.create(
            tenant_id=self.tenant_id, bill_type="advance", admission=self.admission,
            amount=Decimal("100.00"),
        )
        self.assertIsNotNone(payment.receipt_number)
        self.assertEqual(payment.applied_amount, Decimal("0.00"))

    def test_existing_ipd_bill_type_rules_unchanged(self):
        from apps.ipd.models import IPDBilling

        bill = IPDBilling.objects.create(tenant_id=self.tenant_id, admission=self.admission)
        payment = BillPayment.objects.create(
            tenant_id=self.tenant_id, bill_type="ipd", ipd_bill=bill, amount=Decimal("50.00"),
        )
        self.assertIsNotNone(payment.receipt_number)
