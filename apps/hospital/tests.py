# apps/hospital/tests.py

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.hospital.models import Hospital
from apps.hospital.serializers import with_letterhead_defaults
from apps.hospital.views import _validate_letterhead_config


def _make_token(tenant_id, user_id):
    """Build a valid Bearer JWT for the DGHMS middleware."""
    payload = {
        "user_id": str(user_id),
        "email": f"{user_id}@test.com",
        "tenant_id": str(tenant_id),
        "tenant_slug": "test",
        "is_super_admin": False,
        "permissions": {"hms.hospital.view_config": "all"},
        "enabled_modules": ["hms"],
        "user_type": "staff",
        "is_patient": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class HospitalConfigAuthTest(APITestCase):
    """P0 regression: hospital config GET endpoints require authentication."""

    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.hospital = Hospital.objects.create(
            tenant_id=self.tenant_id,
            name='Test Hospital',
            type='hospital',
            email='admin@hospital.com',
            phone='0000000000',
            address='',
            city='',
            state='',
            country='India',
            pincode='000000',
            working_hours='24/7',
            has_emergency=True,
            has_pharmacy=True,
            has_laboratory=True,
        )

    def _auth_client(self):
        token = _make_token(self.tenant_id, self.user_id)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_config_get_requires_auth(self):
        self.client.credentials()
        response = self.client.get('/api/hospital/config/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_config_get_authenticated_returns_tenant_data(self):
        self._auth_client()
        response = self.client.get('/api/hospital/config/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], self.hospital.name)

    def test_nav_style_get_requires_auth(self):
        self.client.credentials()
        response = self.client.get('/api/hospital/config/nav-style/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_nav_style_get_authenticated_returns_tenant_data(self):
        self._auth_client()
        response = self.client.get('/api/hospital/config/nav-style/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_letterhead_get_requires_auth(self):
        self.client.credentials()
        response = self.client.get('/api/hospital/config/letterhead/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_letterhead_get_authenticated_returns_tenant_data(self):
        self._auth_client()
        response = self.client.get('/api/hospital/config/letterhead/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        letterhead = response.data['data']['letterhead']
        self.assertEqual(letterhead['alignment'], 'center')
        self.assertEqual(letterhead['left_image']['width_px'], 72)
        self.assertEqual(letterhead['right_image']['height_px'], 72)


class LetterheadImageSlotContractTest(SimpleTestCase):
    def setUp(self):
        self.legacy_config = {
            "show_logo": True,
            "logo_url": "https://example.com/logo.png",
            "show_badge": False,
            "badge_url": "",
            "alignment": "center",
            "show_hairline": True,
            "text_lines": [],
        }

    def test_legacy_images_are_normalized_into_slots(self):
        normalized = with_letterhead_defaults(self.legacy_config)

        self.assertEqual(
            normalized["left_image"],
            {
                "enabled": True,
                "url": "https://example.com/logo.png",
                "width_px": 72,
                "height_px": 72,
            },
        )
        self.assertFalse(normalized["right_image"]["enabled"])

    def test_validator_accepts_configurable_image_slots(self):
        payload = {
            **self.legacy_config,
            "left_image": {
                "enabled": True,
                "url": "data:image/png;base64,abc",
                "width_px": 150,
                "height_px": 52,
            },
            "right_image": {
                "enabled": True,
                "url": "https://example.com/badge.png",
                "width_px": 64,
                "height_px": 64,
            },
        }

        cleaned, error = _validate_letterhead_config(payload)

        self.assertIsNone(error)
        self.assertEqual(cleaned["left_image"]["width_px"], 150)
        self.assertEqual(cleaned["right_image"]["height_px"], 64)

    def test_validator_rejects_oversized_image_slot(self):
        payload = {
            **self.legacy_config,
            "left_image": {
                "enabled": True,
                "url": "https://example.com/logo.png",
                "width_px": 241,
                "height_px": 72,
            },
        }

        cleaned, error = _validate_letterhead_config(payload)

        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "left_image.width_px")
