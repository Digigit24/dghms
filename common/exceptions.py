"""DRF exception handler and custom exceptions for DigiHMS.

The :func:`custom_exception_handler` is wired into ``REST_FRAMEWORK`` settings
and converts common exceptions into the standard envelope shape.
"""

import structlog
from django.db import IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.views import exception_handler
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    NotFound,
    ValidationError as DRFValidationError,
    MethodNotAllowed,
    Throttled,
)

from . import error_codes
from .responses import error_response

log = structlog.get_logger(__name__)


def custom_exception_handler(exc, context):
    """DRF-compatible exception handler returning standardized envelopes.

    Handles DRF exceptions, Django validation errors, database integrity
    errors, and unexpected exceptions. Falls back to DRF's default handler
    when it produces a response, then re-wraps if needed.
    """
    response = exception_handler(exc, context)

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        code = error_codes.JWT_INVALID if isinstance(exc, AuthenticationFailed) else error_codes.JWT_MISSING
        return error_response(
            code=code,
            message=str(exc) or "Authentication required.",
            status=401,
        )

    if isinstance(exc, PermissionDenied):
        return error_response(
            code=error_codes.PERMISSION_DENIED,
            message=str(exc) or "Permission denied.",
            status=403,
        )

    if isinstance(exc, NotFound):
        return error_response(
            code=error_codes.NOT_FOUND,
            message=str(exc) or "Resource not found.",
            status=404,
        )

    if isinstance(exc, MethodNotAllowed):
        return error_response(
            code=error_codes.METHOD_NOT_ALLOWED,
            message=str(exc),
            status=405,
        )

    if isinstance(exc, Throttled):
        return error_response(
            code=error_codes.RATE_LIMIT_EXCEEDED,
            message=str(exc),
            status=429,
        )

    if isinstance(exc, DRFValidationError):
        detail = exc.detail if hasattr(exc, "detail") else str(exc)
        return error_response(
            code=error_codes.VALIDATION_ERROR,
            message="Validation failed.",
            status=400,
            detail=detail,
        )

    if isinstance(exc, DjangoValidationError):
        messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
        return error_response(
            code=error_codes.VALIDATION_ERROR,
            message="Validation failed.",
            status=400,
            detail=messages,
        )

    if isinstance(exc, IntegrityError):
        return error_response(
            code=error_codes.INTEGRITY_ERROR,
            message="A database integrity error occurred. Possible duplicate.",
            status=409,
        )

    if response is not None:
        # Re-wrap any remaining DRF response in our envelope.
        return error_response(
            code=error_codes.INTERNAL_SERVER_ERROR,
            message=response.reason_phrase or "Request failed.",
            status=response.status_code,
            detail=response.data,
        )

    # Unknown / unhandled exception - log the full traceback so it appears in
    # the Django server console, then return a safe generic response.
    log.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        exc_info=True,
    )
    return error_response(
        code=error_codes.INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred.",
        status=500,
    )


class CeliyoAPIError(Exception):
    """Base class for explicit business-rule exceptions."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class RecordLockedError(CeliyoAPIError):
    """Raised when a clinical record is locked and cannot be modified."""

    def __init__(self, message="This clinical record is locked and cannot be edited."):
        super().__init__(
            code="RECORD_ALREADY_LOCKED",
            message=message,
            status=422,
        )
