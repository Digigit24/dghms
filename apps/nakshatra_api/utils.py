# apps/nakshatra_api/utils.py

import hashlib


def hash_capi_data(data):
    """
    Hashes the user data (email, phone, name) as required by Meta CAPI.

    Args:
        data: The data string to hash (email, phone, first name, last name, etc.)

    Returns:
        str: SHA256 hashed string or None if data is empty
    """
    if not data:
        return None
    # Must be lowercased and trimmed before hashing
    data_to_hash = data.strip().lower().encode('utf-8')
    return hashlib.sha256(data_to_hash).hexdigest()


def create_meta_user_data_payload(form_data, request):
    """
    Creates the user_data object with required hashed fields,
    plus IP and User Agent from the request.

    Args:
        form_data: Dictionary containing form data (fname, lname, email, phone)
        request: Django request object to extract IP and User Agent

    Returns:
        dict: User data payload for Meta CAPI with hashed PII and client info
    """
    # Hashing customer information
    hashed_email = hash_capi_data(form_data.get('email'))
    hashed_phone = hash_capi_data(form_data.get('phone'))
    hashed_fname = hash_capi_data(form_data.get('fname'))
    hashed_lname = hash_capi_data(form_data.get('lname'))

    # Capture client IP and User Agent from headers
    user_data = {
        'client_ip_address': request.META.get('REMOTE_ADDR'),
        'client_user_agent': request.META.get('HTTP_USER_AGENT'),
    }

    # Add hashed fields only if they exist
    if hashed_email:
        user_data['em'] = [hashed_email]
    if hashed_phone:
        user_data['ph'] = [hashed_phone]
    if hashed_fname:
        user_data['fn'] = [hashed_fname]
    if hashed_lname:
        user_data['ln'] = [hashed_lname]

    return user_data
