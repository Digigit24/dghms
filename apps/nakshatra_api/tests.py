# apps/nakshatra_api/tests.py

from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
import json


class NakshatraFormSubmitTestCase(TestCase):
    """Test cases for the Nakshatra form submission endpoint"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        # Use the name defined in the app's urls.py
        self.url = '/api/nakshatra/submit/'
        self.valid_form_data = {
            'fname': 'Test',
            'lname': 'User',
            'email': 'test@nakshatra.com',
            'phone': '+918446013011',
            'services': 'In_Vitro_Fertilization',
            'date': '2025-12-25',
            'client_event_id': 'nakshatra-test-event-123'
        }

    @patch('apps.nakshatra_api.views.requests.post')
    def test_successful_form_submission(self, mock_post):
        """Test successful form submission with mocked API calls"""
        # Mock successful responses from both Custom API and Meta CAPI
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        response = self.client.post(self.url, self.valid_form_data)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')
        self.assertIn('submitted', response_data['message'].lower())

    @patch('apps.nakshatra_api.views.requests.post')
    def test_form_submission_with_custom_api_failure(self, mock_post):
        """Test that form submission succeeds even if Custom API fails"""
        # Mock Custom API failure but Meta CAPI success
        mock_post.side_effect = [
            MagicMock(status_code=500, text='Custom API Error'),  # First call (Custom API)
            MagicMock(status_code=200)  # Second call (Meta CAPI)
        ]

        response = self.client.post(self.url, self.valid_form_data)

        # Should still return success
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(response_data['status'], 'success')

    @patch('apps.nakshatra_api.views.requests.post')
    def test_form_submission_with_meta_capi_failure(self, mock_post):
        """Test that form submission succeeds even if Meta CAPI fails"""
        # Mock Custom API success but Meta CAPI failure
        mock_post.side_effect = [
            MagicMock(status_code=200),  # First call (Custom API)
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

    @patch('apps.nakshatra_api.views.requests.post')
    def test_form_submission_with_missing_fields(self, mock_post):
        """Test form submission with missing fields still works"""
        # Mock successful API responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        incomplete_data = {
            'fname': 'Partial',
            'email': 'partial@example.com'
        }

        response = self.client.post(self.url, incomplete_data)

        # Should still return 200 (endpoint doesn't validate required fields)
        self.assertEqual(response.status_code, 200)
