"""Cloudflare cache purge helpers.

Reads ``CLOUDFLARE_ZONE_ID`` and ``CLOUDFLARE_API_TOKEN`` from Django settings
(populated from environment variables in hms/settings.py; both default to
empty). When unconfigured, every helper is a safe no-op that logs a warning —
nothing in the request path may ever break because Cloudflare is not set up.

Nothing calls these automatically yet; use directly or via the Celery tasks
``common.tasks.purge_cdn_urls`` / ``common.tasks.purge_cdn_everything``.
"""

from __future__ import annotations

import requests
import structlog
from django.conf import settings

log = structlog.get_logger(__name__)

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
REQUEST_TIMEOUT_SECONDS = 15


def _credentials() -> tuple[str, str]:
    zone_id = getattr(settings, "CLOUDFLARE_ZONE_ID", "") or ""
    api_token = getattr(settings, "CLOUDFLARE_API_TOKEN", "") or ""
    return zone_id, api_token


def _purge(payload: dict) -> bool:
    """POST a purge payload to the Cloudflare purge_cache endpoint."""
    zone_id, api_token = _credentials()
    if not zone_id or not api_token:
        log.warning(
            "cloudflare_purge_skipped_not_configured",
            hint="Set CLOUDFLARE_ZONE_ID and CLOUDFLARE_API_TOKEN in the environment.",
        )
        return False

    response = requests.post(
        f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/purge_cache",
        json=payload,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}

    success = bool(response.ok and body.get("success"))
    if success:
        log.info(
            "cloudflare_purge_succeeded",
            status_code=response.status_code,
            purge_everything=payload.get("purge_everything", False),
            url_count=len(payload.get("files", [])),
        )
    else:
        log.error(
            "cloudflare_purge_failed",
            status_code=response.status_code,
            errors=body.get("errors"),
        )
    return success


def purge_urls(urls: list[str]) -> bool:
    """Purge specific URLs from the Cloudflare cache.

    Args:
        urls: Fully-qualified URLs (max 30 per Cloudflare API call; larger
            lists are chunked automatically).

    Returns:
        True if every chunk purged successfully (False if unconfigured).
    """
    if not urls:
        return True

    chunk_size = 30  # Cloudflare API limit per purge call
    all_ok = True
    for i in range(0, len(urls), chunk_size):
        chunk = urls[i:i + chunk_size]
        all_ok = _purge({"files": chunk}) and all_ok
    return all_ok


def purge_everything() -> bool:
    """Purge the entire Cloudflare zone cache.

    Use sparingly (e.g. after a frontend deploy). Returns False when
    unconfigured or when the API call fails.
    """
    return _purge({"purge_everything": True})
