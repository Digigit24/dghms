"""Authentication and activity middleware for DigiHMS.

``JWTAuthenticationMiddleware`` validates Bearer tokens issued by
admin.celiyo.com and attaches JWT claims to the request.

``ActivityLogMiddleware`` asynchronously records requests to sensitive
endpoints for audit purposes.
"""

import queue
import threading

import jwt
import structlog
from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from .auth_backends import TenantUser
from . import error_codes

logger = structlog.get_logger(__name__)

# Thread-local storage for tenant_id and request (used by auth backends and
# any code that needs request context outside of a view).
_thread_locals = threading.local()

# Publishing a Celery task performs broker IO.  Keep that IO off the request
# thread and bound the queue so an unavailable broker cannot grow memory
# without limit.  The daemon worker is started lazily on the first audit event.
_activity_log_queue = queue.Queue(maxsize=256)
_activity_log_worker_started = False
_activity_log_worker_lock = threading.Lock()


def _publish_activity_log_entries():
    while True:
        payload = _activity_log_queue.get()
        try:
            from apps.activity.tasks import write_activity_log_entry

            # A background worker may retry later; publishing itself should not
            # run Celery's long broker-reconnect loop.
            write_activity_log_entry.apply_async(kwargs=payload, retry=False)
        except Exception as exc:
            logger.error(
                "activity_log_enqueue_failed",
                path=payload.get("path"),
                error=str(exc),
            )
        finally:
            _activity_log_queue.task_done()


def _ensure_activity_log_worker():
    global _activity_log_worker_started
    if _activity_log_worker_started:
        return
    with _activity_log_worker_lock:
        if _activity_log_worker_started:
            return
        worker = threading.Thread(
            target=_publish_activity_log_entries,
            name="activity-log-publisher",
            daemon=True,
        )
        worker.start()
        _activity_log_worker_started = True


def _enqueue_activity_log(payload):
    _ensure_activity_log_worker()
    try:
        _activity_log_queue.put_nowait(payload)
    except queue.Full:
        logger.warning(
            "activity_log_queue_full",
            path=payload.get("path"),
            maxsize=_activity_log_queue.maxsize,
        )


def get_current_tenant_id():
    """Get the current tenant_id from thread-local storage."""
    return getattr(_thread_locals, "tenant_id", None)


def set_current_tenant_id(tenant_id):
    """Set the current tenant_id in thread-local storage."""
    _thread_locals.tenant_id = tenant_id


def get_current_request():
    """Get the current request from thread-local storage."""
    return getattr(_thread_locals, "request", None)


def set_current_request(request):
    """Set the current request in thread-local storage."""
    _thread_locals.request = request


def _clean_public_path(path, public_prefixes, exact_paths):
    """Return True if ``path`` is public and should skip JWT validation."""
    if path in exact_paths:
        return True
    return any(path.startswith(prefix) for prefix in public_prefixes)


def middleware_error_response(code, message, status=400, field=None, detail=None):
    """Return a JSON error response from middleware.

    DRF Response objects are finalized by DRF views. Middleware runs before DRF,
    so returning a DRF Response here can raise accepted_renderer errors.
    """
    return JsonResponse(
        {
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "field": field,
                "detail": detail or {},
            },
        },
        status=status,
    )


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """Validates SuperAdmin JWT tokens and attaches claims to the request."""

    # Public paths that don't require authentication (prefix match).
    PUBLIC_PATHS = [
        "/api/docs",
        "/api/redoc",
        "/api/schema",
        "/admin",
        "/auth/",
        "/api/nuviformsubmit",
        "/api/nakshatra/",
        "/api/orders/webhooks/razorpay/",
        "/static/",
        "/media/",
        "/health/",
    ]

    # Exact match paths (must match exactly, not just startswith).
    EXACT_PUBLIC_PATHS = [
        "/",
        "/api/auth/login/",
        "/api/auth/token/refresh/",
        "/api/auth/token/verify/",
    ]

    def process_request(self, request):
        set_current_request(request)

        if _clean_public_path(
            request.path, self.PUBLIC_PATHS, self.EXACT_PUBLIC_PATHS
        ):
            return None

        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header:
            logger.warning(
                "jwt_missing_header",
                path=request.path,
                method=request.method,
            )
            return middleware_error_response(
                code=error_codes.JWT_MISSING,
                message="Authorization header required.",
                status=401,
            )

        try:
            scheme, token = auth_header.split(" ", 1)
        except ValueError:
            logger.warning(
                "jwt_malformed_header",
                path=request.path,
            )
            return middleware_error_response(
                code=error_codes.JWT_MALFORMED,
                message="Invalid authorization header format. Use 'Bearer <token>'.",
                status=401,
            )

        if scheme.lower() != "bearer":
            logger.warning(
                "jwt_invalid_scheme",
                path=request.path,
                scheme=scheme,
            )
            return middleware_error_response(
                code=error_codes.JWT_MALFORMED,
                message="Invalid authorization scheme. Use Bearer token.",
                status=401,
            )

        secret_key = getattr(settings, "JWT_SECRET_KEY", None)
        algorithm = getattr(settings, "JWT_ALGORITHM", "HS256")
        leeway = getattr(settings, "JWT_LEEWAY", 30)

        if not secret_key:
            logger.error("jwt_secret_not_configured")
            return middleware_error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="JWT secret not configured.",
                status=500,
            )

        try:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[algorithm],
                leeway=leeway,
            )
        except jwt.ExpiredSignatureError:
            logger.warning(
                "jwt_expired",
                path=request.path,
            )
            return middleware_error_response(
                code=error_codes.JWT_EXPIRED,
                message="Token has expired.",
                status=401,
            )
        except jwt.InvalidTokenError as exc:
            logger.warning(
                "jwt_invalid",
                path=request.path,
                error=str(exc),
            )
            return middleware_error_response(
                code=error_codes.JWT_INVALID,
                message=f"Invalid token: {exc}",
                status=401,
            )

        required_fields = [
            "user_id",
            "email",
            "tenant_id",
            "tenant_slug",
            "is_super_admin",
            "permissions",
            "enabled_modules",
        ]
        missing = [field for field in required_fields if field not in payload]
        if missing:
            logger.error(
                "jwt_missing_claims",
                path=request.path,
                missing=missing,
            )
            return middleware_error_response(
                code=error_codes.JWT_INVALID,
                message=f"Missing required token claims: {', '.join(missing)}",
                status=401,
            )

        enabled_modules = payload.get("enabled_modules", [])
        if "hms" not in enabled_modules:
            logger.warning(
                "module_not_enabled",
                path=request.path,
                email=payload.get("email"),
                modules=enabled_modules,
            )
            return middleware_error_response(
                code=error_codes.MODULE_NOT_ENABLED,
                message="HMS module not enabled for this user.",
                status=403,
            )

        # Attach JWT claims to the request.
        request.user_id = payload["user_id"]
        request.email = payload["email"]
        request.tenant_id = payload["tenant_id"]
        request.tenant_slug = payload["tenant_slug"]
        request.roles = payload.get("roles", [])
        # Treat jwt is_super_admin OR any admin role as a super-admin for permission bypass
        _admin_roles = {"admin", "superadmin", "hospital_admin", "super_admin"}
        _is_role_admin = bool(set(r.lower() for r in request.roles) & _admin_roles)
        request.is_super_admin = bool(payload.get("is_super_admin", False)) or _is_role_admin
        request.permissions = payload["permissions"]
        request.enabled_modules = enabled_modules
        request.user_type = payload.get("user_type", "staff")
        request.is_patient = bool(payload.get("is_patient", False))

        # Optional tenant override headers (super-admin only or same tenant).
        requested_tenant_id = (
            request.META.get("HTTP_X_TENANT_ID")
            or request.META.get("HTTP_TENANTTOKEN")
        )
        if requested_tenant_id:
            if request.is_super_admin or str(request.tenant_id) == str(
                requested_tenant_id
            ):
                request.tenant_id = requested_tenant_id
            else:
                logger.warning(
                    "tenant_override_denied",
                    email=request.email,
                    token_tenant=str(request.tenant_id),
                    requested_tenant=str(requested_tenant_id),
                )
                return middleware_error_response(
                    code=error_codes.TENANT_MISMATCH,
                    message="You can only access your own tenant.",
                    status=403,
                )

        x_tenant_slug = request.META.get("HTTP_X_TENANT_SLUG")
        if x_tenant_slug:
            request.tenant_slug = x_tenant_slug

        set_current_tenant_id(request.tenant_id)

        # Intentional: set request.user to a TenantUser so that DRF's
        # authentication pipeline and the legacy Django admin site work without
        # a local User model. New clinical/webhook code must use request.user_id
        # and request.tenant_id (from JWT) — never request.user — for business
        # logic. See AGENTS.md Rule 2 and architecture decision D-01.
        user_payload = payload.copy()
        user_payload["tenant_id"] = request.tenant_id
        user_payload["tenant_slug"] = request.tenant_slug
        request.user = TenantUser(user_payload)
        request._cached_user = request.user

        logger.info(
            "jwt_auth_success",
            path=request.path,
            email=request.email,
            tenant_id=str(request.tenant_id),
            user_type=request.user_type,
        )
        return None


class CustomAuthenticationMiddleware(MiddlewareMixin):
    """Supplement middleware that copies TenantUser attributes onto the request.

    This runs after Django's ``AuthenticationMiddleware`` and ensures that
    requests authenticated via session (Django admin) carry the same JWT-style
    attributes as API requests.
    """

    def process_request(self, request):
        from django.contrib.auth.models import AnonymousUser

        user = getattr(request, "user", None)
        if user is None or isinstance(user, AnonymousUser):
            return None

        if isinstance(user, TenantUser):
            request.user_id = getattr(user, "_original_id", user.id)
            request.email = user.email
            request.tenant_id = user.tenant_id
            request.tenant_slug = user.tenant_slug
            request.is_super_admin = user.is_super_admin
            request.permissions = user.permissions
            request.enabled_modules = user.enabled_modules
            request.roles = getattr(user, "roles", [])
            request.user_type = user.user_type
            request.is_patient = user.is_patient
            set_current_tenant_id(request.tenant_id)
            logger.debug(
                "custom_auth_session_ok",
                email=request.email,
                tenant_id=str(request.tenant_id),
            )

        return None


class ActivityLogMiddleware(MiddlewareMixin):
    """Asynchronously log requests to sensitive endpoints.

    Logs requests whose path contains ``/clinical/``, ``/knowledge/``,
    ``/webhooks/``, or ``/activity/``.  The actual write is delegated to the
    Celery task ``apps.activity.tasks.write_activity_log_entry`` so the request
    path is never blocked by audit IO.
    """

    LOGGED_PREFIXES = (
        "/api/clinical/",
        "/api/knowledge/",
        "/api/webhooks/",
        "/api/activity/",
    )

    def process_response(self, request, response):
        path = getattr(request, "path", "")
        if not any(path.startswith(prefix) for prefix in self.LOGGED_PREFIXES):
            return response

        # Avoid logging activity requests themselves to prevent loops.
        if path.startswith("/api/activity/"):
            return response

        user_id = getattr(request, "user_id", None)
        tenant_id = getattr(request, "tenant_id", None)

        _enqueue_activity_log(
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "user_id": str(user_id) if user_id else None,
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "ip_address": request.META.get("REMOTE_ADDR"),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            }
        )

        return response

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
