#!/usr/bin/env python
"""
Production test script for the Nakshatra form submission endpoint
Usage: python test_nakshatra_prod.py
"""

import requests
import uuid

# Configuration
BASE_URL = "https://hms.celiyo.com"
ENDPOINT = f"{BASE_URL}/api/nakshatra/submit/"
X_TENANT_ID = "d2bcd1ee-e5c5-4c9f-bff2-aaf901d40440"

# Test data
form_data = {
    'fname': 'Production',
    'lname': 'Test',
    'email': 'prod-test@nakshatra.com',
    'phone': '+918446013011',
    'services': 'In_Vitro_Fertilization',
    'date': '2025-12-25',
    'client_event_id': f"nakshatra-{uuid.uuid4()}"  # Generate unique event ID
}

headers = {
    'X-TENANT-ID': X_TENANT_ID
}

print(f"Testing Production Endpoint: {ENDPOINT}")
print(f"Tenant ID: {X_TENANT_ID}")
print(f"Sending data: {form_data}")
print("-" * 60)

try:
    # Make POST request
    response = requests.post(ENDPOINT, data=form_data, headers=headers, timeout=30)

    print(f"Status Code: {response.status_code}")
    print(f"Response Content: {response.text}")

    if response.status_code == 200:
        print("\n✅ SUCCESS! Nakshatra form submitted successfully to production.")
    else:
        print(f"\n❌ FAILED with status code {response.status_code}")
        if response.status_code == 401 or response.status_code == 403:
            print("Note: If you get 401/403, ensure the endpoint path is registered in the public paths of JWTAuthenticationMiddleware.")

except requests.exceptions.RequestException as e:
    print(f"\n❌ ERROR: {e}")
