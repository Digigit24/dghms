"""Standardized API response helpers for DigiHMS.

All DRF views should return responses produced by :func:`success_response`,
:func:`error_response`, or :func:`action_response` to keep the envelope shape
consistent across the API.
"""

from rest_framework.response import Response


def success_response(data=None, message=None, status=200):
    """Return a successful envelope response.

    Args:
        data: Serializable payload. Defaults to ``None``.
        message: Optional human-readable message.
        status: HTTP status code. Defaults to 200.
    """
    payload = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status)


def error_response(code, message, status=400, field=None, detail=None):
    """Return an error envelope response.

    The error is nested under the ``error`` key per the architecture standard
    (CLAUDE.md §5): ``{success, error: {code, message, field, detail}}``.

    Args:
        code: SCREAMING_SNAKE_CASE error code from ``common.error_codes``.
        message: Human-readable error message.
        status: HTTP status code. Defaults to 400.
        field: Optional field name that caused the error.
        detail: Optional dict with extra context.
    """
    error_body: dict = {"code": code, "message": message, "field": field, "detail": detail or {}}
    return Response({"success": False, "error": error_body}, status=status)


def action_response(message, status=200, data=None):
    """Return a lightweight action confirmation response.

    Useful for POST/PUT/PATCH/DELETE actions that do not return a resource body.
    """
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return Response(body, status=status)
