# apps/nuviapi/tests.py

from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
import json


class NuviFormSubmitTestCase(TestCase):
    """Test cases for the Nuvi form submission endpoint"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.url = reverse('nuviapi:nuvi_form_submit')
        self.valid_form_data = {
            'fname': 'John',
            'lname': 'Doe',
            'email': 'john.doe@example.com',
            'phone': '+1234567890',
            'services': 'Consultation',
            'date': '2025-12-20',
            'client_event_id': 'test-event-123'
        }

    @patch('apps.nuviapi.views.requests.post')
    def test_successful_form_submission(self, mock_post):
        """Test successful form submission with mocked API calls"""
        # Mock successful responses from both Google Sheets and Meta CAPI
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        response = self.client.post(self.url, self.valid_form_data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        self.assertIn('submitted', response_data['message'].lower())

    @patch('apps.nuviapi.views.requests.post')
    def test_form_submission_with_google_sheets_failure(self, mock_post):
        """Test that form submission succeeds even if Google Sheets fails"""
        # Mock Google Sheets failure but Meta CAPI success
        mock_post.side_effect = [
            MagicMock(status_code=500, text='Google Sheets Error'),  # First call (Google Sheets)
            MagicMock(status_code=200)  # Second call (Meta CAPI)
        ]

        response = self.client.post(self.url, self.valid_form_data)

        # Should still return success
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')

    @patch('apps.nuviapi.views.requests.post')
    def test_form_submission_with_meta_capi_failure(self, mock_post):
        """Test that form submission succeeds even if Meta CAPI fails"""
        # Mock Google Sheets success but Meta CAPI failure
        mock_post.side_effect = [
            MagicMock(status_code=200),  # First call (Google Sheets)
            MagicMock(status_code=400, text='Meta CAPI Error')  # Second call (Meta CAPI)
        ]

        response = self.client.post(self.url, self.valid_form_data)

        # Should still return success
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')

    def test_get_request_not_allowed(self):
        """Test that GET requests are not allowed"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    @patch('apps.nuviapi.views.requests.post')
    def test_form_submission_with_missing_fields(self, mock_post):
        """Test form submission with missing fields still works"""
        # Mock successful API responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        incomplete_data = {
            'fname': 'John',
            'email': 'john@example.com'
            # Missing other fields
        }

        response = self.client.post(self.url, incomplete_data)

        # Should still return 200 (endpoint doesn't validate required fields)
        self.assertEqual(response.status_code, 200)


class UtilsTestCase(TestCase):
    """Test cases for utility functions"""

    def test_hash_capi_data(self):
        """Test that data is hashed correctly"""
        from apps.nuviapi.utils import hash_capi_data

        # Test with valid email
        email = 'test@example.com'
        hashed = hash_capi_data(email)
        self.assertIsNotNone(hashed)
        self.assertEqual(len(hashed), 64)  # SHA256 produces 64 character hex string

        # Test with None
        self.assertIsNone(hash_capi_data(None))

        # Test with empty string
        self.assertIsNone(hash_capi_data(''))

        # Test that same input produces same hash
        email2 = 'test@example.com'
        hashed2 = hash_capi_data(email2)
        self.assertEqual(hashed, hashed2)

        # Test case insensitivity and trimming
        email3 = '  TEST@EXAMPLE.COM  '
        hashed3 = hash_capi_data(email3)
        self.assertEqual(hashed, hashed3)

    def test_create_meta_user_data_payload(self):
        """Test Meta user data payload creation"""
        from apps.nuviapi.utils import create_meta_user_data_payload
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.post('/test/', {
            'fname': 'John',
            'lname': 'Doe',
            'email': 'john@example.com',
            'phone': '+1234567890'
        })

        form_data = {
            'fname': 'John',
            'lname': 'Doe',
            'email': 'john@example.com',
            'phone': '+1234567890'
        }

        payload = create_meta_user_data_payload(form_data, request)

        # Check that required fields are present
        self.assertIn('client_ip_address', payload)
        self.assertIn('client_user_agent', payload)

        # Check that hashed fields are present
        self.assertIn('em', payload)
        self.assertIn('fn', payload)
        self.assertIn('ln', payload)
        self.assertIn('ph', payload)

        # Check that hashed fields are lists
        self.assertIsInstance(payload['em'], list)
        self.assertIsInstance(payload['fn'], list)
        self.assertIsInstance(payload['ln'], list)
        self.assertIsInstance(payload['ph'], list)
