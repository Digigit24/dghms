
from django.test import SimpleTestCase

from apps.doctors.serializers import DoctorProfileListSerializer


class DoctorMasterContractTest(SimpleTestCase):
    def test_list_response_contains_every_editable_drawer_field(self):
        fields = set(DoctorProfileListSerializer().fields)
        self.assertTrue({
            "license_issuing_authority",
            "license_issue_date",
            "license_expiry_date",
            "follow_up_fee",
            "languages_spoken",
        }.issubset(fields))
