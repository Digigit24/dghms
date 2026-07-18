import datetime
import uuid

import jwt
from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from apps.doctors.models import DoctorProfile
from apps.ipd.models import Admission, Bed, Ward
from apps.patients.models import PatientProfile


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
