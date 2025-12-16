#!/usr/bin/env python
"""
Simple script to test the Nuvi form submission endpoint
Usage: python test_endpoint.py
"""

import requests
import uuid

# Configuration
BASE_URL = "https://hms.celiyo.com"  # Change to your server URL
ENDPOINT = f"{BASE_URL}/api/nuviformsubmit"

# Test data
form_data = {
    'fname': 'John',
    'lname': 'Doe',
    'email': 'john.doe@example.com',
    'phone': '+1234567890',
    'services': 'Consultation',
    'date': '2025-12-20',
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
