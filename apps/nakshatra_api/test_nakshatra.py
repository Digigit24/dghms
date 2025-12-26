#!/usr/bin/env python
"""
Simple script to test the Nakshatra form submission endpoint
Usage: python test_nakshatra.py
"""

import requests
import uuid

# Configuration
BASE_URL = "http://127.0.0.1:8000"  # Change to your server URL
ENDPOINT = f"{BASE_URL}/api/nakshatra/submit/"

# Test data
form_data = {
    'fname': 'Test',
    'lname': 'User',
    'email': 'test@example.com',
    'phone': '+911234567890',
    'services': 'In_Vitro_Fertilization',
    'date': '2025-12-25',
    'client_event_id': str(uuid.uuid4())  # Generate unique event ID
}

print(f"Testing endpoint: {ENDPOINT}")
print(f"Sending data: {form_data}")
print("-" * 60)

try:
    # Make POST request (no auth header needed)
    response = requests.post(ENDPOINT, data=form_data, timeout=30)

    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code == 200:
        print("\n✅ SUCCESS! Form submitted successfully.")
    else:
        print(f"\n❌ FAILED with status code {response.status_code}")

except requests.exceptions.RequestException as e:
    print(f"\n❌ ERROR: {e}")
