# apps/hospital/tests.py

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.hospital.models import Hospital


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
