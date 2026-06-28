"""Management command to export the OpenAPI schema to docs/openapi.json."""

import json
import os

import structlog
from django.core.management.base import BaseCommand
from django.conf import settings
from drf_spectacular.renderers import OpenApiJsonRenderer
from drf_spectacular.generators import SchemaGenerator

logger = structlog.get_logger(__name__)


class Command(BaseCommand):
    help = "Export the DigiHMS OpenAPI schema to docs/openapi.json"

    def handle(self, *args, **options):
        generator = SchemaGenerator()
        schema = generator.get_schema(request=None, public=True)
        renderer = OpenApiJsonRenderer()
        rendered = renderer.render(schema, renderer_context={})

        docs_dir = os.path.join(settings.BASE_DIR, "docs")
        os.makedirs(docs_dir, exist_ok=True)
        output_path = os.path.join(docs_dir, "openapi.json")

        # Rendered may be bytes; normalize to a pretty-printed JSON string.
        if isinstance(rendered, bytes):
            rendered = rendered.decode("utf-8")

        parsed = json.loads(rendered)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2)

        logger.info("openapi_exported", path=output_path)
        self.stdout.write(self.style.SUCCESS(f"OpenAPI schema exported to {output_path}"))
