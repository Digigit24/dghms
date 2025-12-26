import requests
import uuid

BASE_URL = "https://hms.celiyo.com"
ENDPOINT = f"{BASE_URL}/api/nuviformsubmit"
X_TENANT_ID = "d2bcd1ee-e5c5-4c9f-bff2-aaf901d40440"

form_data = {
    'fname': 'Nuvi',
    'lname': 'Test',
    'email': 'nuvi-test@example.com',
    'phone': '+1234567890',
    'services': 'Consultation',
    'date': '2025-12-25',
    'client_event_id': str(uuid.uuid4())
}

headers = {
    'X-TENANT-ID': X_TENANT_ID
}

print(f"Testing existing Nuvi endpoint: {ENDPOINT}")
try:
    response = requests.post(ENDPOINT, data=form_data, headers=headers, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
