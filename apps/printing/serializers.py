"""Serializers for the printing app.

These exist primarily to give drf-spectacular named response/request schemas
(CLAUDE.md §11 forbids inline dicts in ``@extend_schema``). The actual
preview/render endpoints return raw ``text/html`` or ``application/pdf``
bodies rather than serialized JSON, so these serializers only document the
batch request body and the shared error envelope shape used on failure
paths.
"""

from rest_framework import serializers


class PrintBatchRequestSerializer(serializers.Serializer):
    """Request body for ``POST /api/print/batch/``."""

    form = serializers.CharField(
        max_length=64,
        help_text="Registered print form code, e.g. 'progress_sheet'.",
    )
    record_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="ClinicalRecord (or Admission, for admission_form) ids to render, in order. Max 100.",
    )
    letterhead = serializers.BooleanField(
        default=True,
        help_text="Whether to render the tenant letterhead header on each page.",
    )
    language = serializers.ChoiceField(
        choices=["en", "mr"],
        default="en",
        help_text="Language for form labels, where the form/section defines a translation.",
    )


class DocumentBatchPrintRequestSerializer(serializers.Serializer):
    """Request body for ``POST /api/print/documents/batch/``.

    Renders each selected consent/stationery/certificate document template for
    the given encounter and merges them into a single PDF.
    """

    template_codes = serializers.ListField(
        child=serializers.CharField(max_length=64),
        min_length=1,
        help_text="ClinicalDocumentTemplate codes to render, in print order. Max 100.",
    )
    encounter_type = serializers.ChoiceField(
        choices=["ipd_admission", "opd_visit"],
        help_text="Encounter the documents belong to.",
    )
    encounter_id = serializers.IntegerField(
        help_text="Admission id (ipd_admission) or Visit id (opd_visit).",
    )
    letterhead = serializers.BooleanField(
        default=True,
        help_text="Whether to render the tenant letterhead header on each page.",
    )
    language = serializers.ChoiceField(
        choices=["en", "mr"],
        default="en",
        help_text="Language for document labels where a translation exists.",
    )


class PrintErrorDetailSerializer(serializers.Serializer):
    """Documents the standard CLAUDE.md §5 error envelope ``error`` object."""

    code = serializers.CharField()
    message = serializers.CharField()
    field = serializers.CharField(allow_null=True)
    detail = serializers.DictField()


class PrintErrorResponseSerializer(serializers.Serializer):
    """Documents the standard CLAUDE.md §5 error envelope."""

    success = serializers.BooleanField(default=False)
    error = PrintErrorDetailSerializer()
