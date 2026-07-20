"""API views for server-side print rendering (WeasyPrint).

Three endpoints:

- GET  /api/print/preview/  -> text/html   (iframe live preview)
- GET  /api/print/render/   -> application/pdf (single record)
- POST /api/print/batch/    -> application/pdf (many records of the same
                                repeatable form merged into one PDF)

All record lookups are scoped to ``request.tenant_id`` (never a
client-supplied identifier), per CLAUDE.md §3. Permission reuses the same
checks as the source viewsets: ``hms.clinical.view`` for ClinicalRecord-backed
forms (nursing_paper, monitoring_chart, progress_sheet, clinical_form — see
apps/clinical/views.py::ClinicalRecordViewSet.get_queryset),
``hms.ipd.view`` for the Admission-backed admission_form (see
apps/ipd/views.py::AdmissionViewSet, hms_module='ipd'), and
``hms.opd.view`` for the Visit/OPDBill-backed opd_visit_form and opd_bill.
"""

from __future__ import annotations

import time
import uuid

import structlog
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from common import error_codes
from common.permissions import HMSPermissions, IsTenantAuthenticated, check_permission
from common.responses import error_response

from .rendering import (
    DOCUMENT_ENCOUNTER_TYPES,
    FORM_ADMISSION,
    FORM_OPD_BILL,
    FORM_OPD_VISIT,
    FORM_IPD_BILL,
    MAX_DOCUMENT_BATCH_SIZE,
    PdfMergeError,
    PrintFormCodeError,
    PrintNotFoundError,
    render_batch_html,
    render_document_batch_pdf,
    render_pdf_from_html,
    render_print_html,
)
from .serializers import (
    DocumentBatchPrintRequestSerializer,
    PrintBatchRequestSerializer,
    PrintErrorResponseSerializer,
)

log = structlog.get_logger(__name__)

MAX_BATCH_SIZE = 100


class CanViewPrintSource(BasePermission):
    """Checks the permission of the underlying record type for a print request.

    ``admission_form`` and ``ipd_bill`` read an ``Admission``/``IPDBilling``
    (IPD app) so they require ``hms.ipd.view``. ``opd_visit_form`` and
    ``opd_bill`` read a ``Visit``/``OPDBill`` (OPD app) so they require
    ``hms.opd.view``. Every other registered form code reads a
    ``ClinicalRecord`` so it requires ``hms.clinical.view`` — the exact same
    permission gate used by ``ClinicalRecordViewSet.get_queryset()``.
    """

    def has_permission(self, request, view) -> bool:
        form_code = request.query_params.get("form") or (request.data or {}).get("form")
        if form_code in (FORM_ADMISSION, FORM_IPD_BILL):
            return check_permission(request, "hms.ipd.view")
        if form_code in (FORM_OPD_VISIT, FORM_OPD_BILL):
            return check_permission(request, HMSPermissions.OPD_VIEW)
        return check_permission(request, HMSPermissions.CLINICAL_VIEW)


def _parse_common_params(request) -> tuple[str | None, int | None, bool, str, Response | None]:
    """Parse and validate the shared ``form``/``record_id``/``letterhead``/``language`` params.

    Returns ``(form_code, record_id, letterhead, language, error_response)``.
    If validation fails, ``error_response`` is a ready-to-return standard
    envelope response and the other values should be ignored.
    """
    form_code = (request.query_params.get("form") or "").strip()
    record_id_raw = request.query_params.get("record_id")
    letterhead_raw = request.query_params.get("letterhead", "true")
    language = (request.query_params.get("language") or "en").strip().lower()

    if not form_code:
        return None, None, False, language, error_response(
            code=error_codes.INVALID_PAYLOAD,
            message="'form' query parameter is required.",
            status=status.HTTP_400_BAD_REQUEST,
            field="form",
        )

    if not record_id_raw:
        return None, None, False, language, error_response(
            code=error_codes.INVALID_PAYLOAD,
            message="'record_id' query parameter is required.",
            status=status.HTTP_400_BAD_REQUEST,
            field="record_id",
        )

    try:
        record_id = int(record_id_raw)
    except (TypeError, ValueError):
        return None, None, False, language, error_response(
            code=error_codes.INVALID_PAYLOAD,
            message="'record_id' must be an integer.",
            status=status.HTTP_400_BAD_REQUEST,
            field="record_id",
        )

    if language not in ("en", "mr"):
        return None, None, False, language, error_response(
            code=error_codes.INVALID_PAYLOAD,
            message="'language' must be 'en' or 'mr'.",
            status=status.HTTP_400_BAD_REQUEST,
            field="language",
        )

    letterhead = str(letterhead_raw).strip().lower() not in ("false", "0", "no")

    return form_code, record_id, letterhead, language, None


class PrintPreviewView(APIView):
    """Render a single record's print template as raw HTML for iframe preview."""

    permission_classes = [IsTenantAuthenticated, CanViewPrintSource]

    @extend_schema(
        summary="Render a live HTML print preview",
        description=(
            "Renders the print template for one record as raw text/html, for "
            "use in an <iframe> live-preview panel. Not a JSON envelope — the "
            "response body is the HTML document itself. On error (bad form "
            "code, missing/not-found record), returns the standard "
            "{success, error} JSON envelope with an appropriate 4xx status."
        ),
        parameters=[
            OpenApiParameter("form", str, OpenApiParameter.QUERY, required=True,
                              description="Registered print form code."),
            OpenApiParameter("record_id", int, OpenApiParameter.QUERY, required=True,
                              description="ClinicalRecord id (or Admission id for admission_form)."),
            OpenApiParameter("letterhead", bool, OpenApiParameter.QUERY, required=False,
                              description="Whether to render the tenant letterhead header. Default true."),
            OpenApiParameter("language", str, OpenApiParameter.QUERY, required=False,
                              description="'en' or 'mr'. Default 'en'."),
        ],
        responses={200: OpenApiTypes.BINARY, 400: PrintErrorResponseSerializer, 404: PrintErrorResponseSerializer},
        tags=["Print"],
    )
    def get(self, request, *args, **kwargs) -> HttpResponse | Response:
        """GET /api/print/preview/?form=<code>&record_id=<id>&letterhead=&language="""
        form_code, record_id, letterhead, language, err = _parse_common_params(request)
        if err is not None:
            return err

        tenant_id: uuid.UUID = request.tenant_id
        start = time.monotonic()
        try:
            html = render_print_html(form_code, tenant_id, record_id, letterhead, language)
        except PrintFormCodeError as exc:
            return error_response(
                code=error_codes.INVALID_PAYLOAD,
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
                field="form",
            )
        except PrintNotFoundError as exc:
            return error_response(
                code=error_codes.RECORD_NOT_FOUND,
                message=str(exc),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            log.error(
                "print_preview_render_failed",
                tenant_id=str(tenant_id),
                form=form_code,
                record_id=record_id,
                error=str(exc),
            )
            return error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="Failed to render print preview.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "print_pdf_rendered",
            tenant_id=str(tenant_id),
            user_id=str(request.user_id),
            form=form_code,
            record_id=record_id,
            mode="preview_html",
            duration_ms=duration_ms,
        )
        # Plain HttpResponse (not DRF Response): DEFAULT_RENDERER_CLASSES only
        # registers JSONRenderer/BrowsableAPIRenderer, which would otherwise
        # JSON-encode this HTML string instead of serving it as a raw document.
        return HttpResponse(html, content_type="text/html")


class PrintRenderView(APIView):
    """Render a single record's print template through WeasyPrint to a PDF."""

    permission_classes = [IsTenantAuthenticated, CanViewPrintSource]

    @extend_schema(
        summary="Render a single record as a printable PDF",
        description=(
            "Renders the print template for one record through WeasyPrint and "
            "returns application/pdf with Content-Disposition: inline. On "
            "error (bad form code, missing/not-found record), returns the "
            "standard {success, error} JSON envelope with an appropriate 4xx "
            "status instead of a PDF body."
        ),
        parameters=[
            OpenApiParameter("form", str, OpenApiParameter.QUERY, required=True,
                              description="Registered print form code."),
            OpenApiParameter("record_id", int, OpenApiParameter.QUERY, required=True,
                              description="ClinicalRecord id (or Admission id for admission_form)."),
            OpenApiParameter("letterhead", bool, OpenApiParameter.QUERY, required=False,
                              description="Whether to render the tenant letterhead header. Default true."),
            OpenApiParameter("language", str, OpenApiParameter.QUERY, required=False,
                              description="'en' or 'mr'. Default 'en'."),
        ],
        responses={200: OpenApiTypes.BINARY, 400: PrintErrorResponseSerializer, 404: PrintErrorResponseSerializer},
        tags=["Print"],
    )
    def get(self, request, *args, **kwargs) -> HttpResponse | Response:
        """GET /api/print/render/?form=<code>&record_id=<id>&letterhead=&language="""
        form_code, record_id, letterhead, language, err = _parse_common_params(request)
        if err is not None:
            return err

        tenant_id: uuid.UUID = request.tenant_id
        start = time.monotonic()
        try:
            html = render_print_html(form_code, tenant_id, record_id, letterhead, language)
            pdf_bytes = render_pdf_from_html(html)
        except PrintFormCodeError as exc:
            return error_response(
                code=error_codes.INVALID_PAYLOAD,
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
                field="form",
            )
        except PrintNotFoundError as exc:
            return error_response(
                code=error_codes.RECORD_NOT_FOUND,
                message=str(exc),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            log.error(
                "print_pdf_render_failed",
                tenant_id=str(tenant_id),
                form=form_code,
                record_id=record_id,
                error=str(exc),
            )
            return error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="Failed to render PDF.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "print_pdf_rendered",
            tenant_id=str(tenant_id),
            user_id=str(request.user_id),
            form=form_code,
            record_id=record_id,
            mode="render_pdf",
            duration_ms=duration_ms,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{form_code}_{record_id}.pdf"'
        return response


class PrintBatchView(APIView):
    """Merge many records of the same form into a single PDF."""

    permission_classes = [IsTenantAuthenticated, CanViewPrintSource]

    @extend_schema(
        summary="Batch-render many records into one merged PDF",
        description=(
            "Renders every record id in `record_ids` (same `form` code) back "
            "to back into ONE HTML document, with the letterhead repeating on "
            "each page, then converts it with a single WeasyPrint call into "
            "one merged application/pdf response. Capped at 100 records per "
            "request. Primarily used for batch-printing repeatable forms such "
            "as progress/round notes or monitoring chart occurrences for an "
            "encounter."
        ),
        request=PrintBatchRequestSerializer,
        responses={200: OpenApiTypes.BINARY, 400: PrintErrorResponseSerializer, 404: PrintErrorResponseSerializer},
        tags=["Print"],
    )
    def post(self, request, *args, **kwargs) -> HttpResponse | Response:
        """POST /api/print/batch/ {form, record_ids, letterhead, language}"""
        payload = PrintBatchRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        form_code = data["form"]
        record_ids = data["record_ids"]
        letterhead = data["letterhead"]
        language = data["language"]

        if len(record_ids) > MAX_BATCH_SIZE:
            return error_response(
                code=error_codes.INVALID_PAYLOAD,
                message=f"A maximum of {MAX_BATCH_SIZE} record_ids may be printed in one batch.",
                status=status.HTTP_400_BAD_REQUEST,
                field="record_ids",
            )

        tenant_id: uuid.UUID = request.tenant_id
        start = time.monotonic()
        try:
            html = render_batch_html(form_code, tenant_id, record_ids, letterhead, language)
            pdf_bytes = render_pdf_from_html(html)
        except PrintFormCodeError as exc:
            return error_response(
                code=error_codes.INVALID_PAYLOAD,
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
                field="form",
            )
        except PrintNotFoundError as exc:
            return error_response(
                code=error_codes.RECORD_NOT_FOUND,
                message=str(exc),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            log.error(
                "print_batch_render_failed",
                tenant_id=str(tenant_id),
                form=form_code,
                record_count=len(record_ids),
                error=str(exc),
            )
            return error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="Failed to render batch PDF.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "print_pdf_rendered",
            tenant_id=str(tenant_id),
            user_id=str(request.user_id),
            form=form_code,
            record_count=len(record_ids),
            mode="batch_pdf",
            duration_ms=duration_ms,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{form_code}_batch.pdf"'
        return response


class CanPrintDocuments(BasePermission):
    """Permission gate for consent/stationery/certificate batch printing.

    The documents belong to an encounter, so the required permission mirrors
    that encounter's source viewset: ``hms.ipd.view`` for ipd_admission and
    ``hms.opd.view`` for opd_visit. Unknown encounter types are allowed through
    to the view, which returns a clean 400 rather than a 403.
    """

    def has_permission(self, request, view) -> bool:
        encounter_type = (request.data or {}).get("encounter_type")
        if encounter_type == "ipd_admission":
            return check_permission(request, "hms.ipd.view")
        if encounter_type == "opd_visit":
            return check_permission(request, HMSPermissions.OPD_VIEW)
        return True


class ClinicalDocumentBatchPrintView(APIView):
    """Render selected consent/stationery documents and merge them into one PDF."""

    permission_classes = [IsTenantAuthenticated, CanPrintDocuments]

    @extend_schema(
        summary="Batch-print consent/stationery documents into one merged PDF",
        description=(
            "Renders every ClinicalDocumentTemplate in `template_codes` for the "
            "given encounter (each to its own PDF), then merges them page-for-"
            "page into a single application/pdf response with the letterhead on "
            "every page. When a document has no authored print template, a "
            "generic letterhead-aware stationery page is used so the batch "
            "never hard-fails. Capped at 100 documents per request."
        ),
        request=DocumentBatchPrintRequestSerializer,
        responses={200: OpenApiTypes.BINARY, 400: PrintErrorResponseSerializer, 404: PrintErrorResponseSerializer},
        tags=["Print"],
    )
    def post(self, request, *args, **kwargs) -> HttpResponse | Response:
        """POST /api/print/documents/batch/ {template_codes, encounter_type, encounter_id, letterhead, language}"""
        payload = DocumentBatchPrintRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        template_codes = data["template_codes"]
        encounter_type = data["encounter_type"]
        encounter_id = data["encounter_id"]
        letterhead = data["letterhead"]
        language = data["language"]

        if encounter_type not in DOCUMENT_ENCOUNTER_TYPES:
            return error_response(
                code=error_codes.INVALID_PAYLOAD,
                message=f"'encounter_type' must be one of {sorted(DOCUMENT_ENCOUNTER_TYPES)}.",
                status=status.HTTP_400_BAD_REQUEST,
                field="encounter_type",
            )

        if len(template_codes) > MAX_DOCUMENT_BATCH_SIZE:
            return error_response(
                code=error_codes.INVALID_PAYLOAD,
                message=f"A maximum of {MAX_DOCUMENT_BATCH_SIZE} documents may be printed in one batch.",
                status=status.HTTP_400_BAD_REQUEST,
                field="template_codes",
            )

        tenant_id: uuid.UUID = request.tenant_id
        start = time.monotonic()
        try:
            pdf_bytes = render_document_batch_pdf(
                tenant_id, template_codes, encounter_type, encounter_id, letterhead, language
            )
        except PrintFormCodeError as exc:
            return error_response(
                code=error_codes.INVALID_PAYLOAD,
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
                field="encounter_type",
            )
        except PrintNotFoundError as exc:
            return error_response(
                code=error_codes.RECORD_NOT_FOUND,
                message=str(exc),
                status=status.HTTP_404_NOT_FOUND,
            )
        except PdfMergeError as exc:
            failed_index = exc.document_index
            failed_code = (
                template_codes[failed_index]
                if failed_index is not None and failed_index < len(template_codes)
                else None
            )
            log.error(
                "print_document_batch_merge_failed",
                tenant_id=str(tenant_id),
                encounter_type=encounter_type,
                encounter_id=encounter_id,
                document_count=len(template_codes),
                failed_document_index=failed_index,
                failed_document_code=failed_code,
                error=str(exc),
            )
            return error_response(
                code=error_codes.PDF_MERGE_FAILED,
                message="One or more documents could not be merged into a valid A4 PDF.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "document_index": failed_index,
                    "document_code": failed_code,
                },
            )
        except Exception as exc:
            log.error(
                "print_document_batch_render_failed",
                tenant_id=str(tenant_id),
                encounter_type=encounter_type,
                encounter_id=encounter_id,
                document_count=len(template_codes),
                error=str(exc),
            )
            return error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="Failed to render the merged documents PDF.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "print_pdf_rendered",
            tenant_id=str(tenant_id),
            user_id=str(request.user_id),
            encounter_type=encounter_type,
            encounter_id=encounter_id,
            document_count=len(template_codes),
            mode="document_batch_pdf",
            duration_ms=duration_ms,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="documents_batch.pdf"'
        return response
