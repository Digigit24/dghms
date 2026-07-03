"""Cache-Control headers middleware for Cloudflare CDN support.

Policy (see DEPLOYMENT_MANUAL_STEPS.md at the repo root for the matching
Cloudflare dashboard rules):

- Every ``/api/`` response defaults to ``private, no-store`` — API responses
  contain tenant/patient data and must NEVER be cached by the CDN or any
  shared proxy.
- A small allowlist of truly static, tenant-agnostic GET endpoints (OpenAPI
  schema and docs UIs) may be cached publicly for a short time.
- ``/static/`` assets are immutable build artifacts → long public max-age.
- ``/media/`` files may contain patient documents → long *browser* max-age
  but ``private`` so Cloudflare never stores them.

Views that set their own ``Cache-Control`` header are always respected.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

# Tenant-agnostic, non-sensitive GET endpoints that may be publicly cached.
PUBLIC_API_PREFIXES = (
    "/api/schema/",
    "/api/docs/",
    "/api/redoc/",
)

STATIC_PREFIX = "/static/"
MEDIA_PREFIX = "/media/"

STATIC_CACHE_CONTROL = "public, max-age=31536000, immutable"
MEDIA_CACHE_CONTROL = "private, max-age=86400"
PUBLIC_API_CACHE_CONTROL = "public, max-age=3600"
API_CACHE_CONTROL = "private, no-store"


class CDNCacheControlMiddleware:
    """Sets a safe ``Cache-Control`` header on every response.

    Registered in ``MIDDLEWARE`` (hms/settings.py). Runs on the response
    phase, after views/renderers, and never overrides a header that a view
    set explicitly.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Respect explicit view-level cache headers.
        if response.has_header("Cache-Control"):
            return response

        path = request.path
        if path.startswith(STATIC_PREFIX):
            response["Cache-Control"] = STATIC_CACHE_CONTROL
        elif path.startswith(MEDIA_PREFIX):
            response["Cache-Control"] = MEDIA_CACHE_CONTROL
        elif path.startswith(PUBLIC_API_PREFIXES) and request.method in ("GET", "HEAD"):
            response["Cache-Control"] = PUBLIC_API_CACHE_CONTROL
        elif path.startswith("/api/"):
            response["Cache-Control"] = API_CACHE_CONTROL

        return response
