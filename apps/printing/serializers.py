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
