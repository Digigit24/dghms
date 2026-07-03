
from rest_framework import serializers
from .models import Hospital


class HospitalSerializer(serializers.ModelSerializer):
    """Hospital configuration serializer"""
    type_display = serializers.CharField(
        source='get_type_display',
        read_only=True
    )
    full_address = serializers.CharField(read_only=True)
    nav_style_label = serializers.CharField(
        source='get_nav_style_display',
        read_only=True
    )

    letterhead_config = serializers.SerializerMethodField()

    class Meta:
        model = Hospital
        fields = [
            'id', 'name', 'type', 'type_display', 'tagline',
            'email', 'phone', 'alternate_phone', 'website',
            'address', 'city', 'state', 'country', 'pincode',
            'full_address', 'logo', 'working_hours',
            'has_emergency', 'has_pharmacy', 'has_laboratory',
            'registration_number', 'established_date',
            'nav_style', 'nav_style_label',
            'letterhead_config',
            'theme_config',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_letterhead_config(self, obj: Hospital) -> dict:
        """
        Read-time fallback: if the tenant hasn't configured a letterhead yet
        (``letterhead_config`` is empty), compute a sensible default from the
        hospital's existing fields rather than returning ``{}``. This is
        compute-on-read (not persisted here) — see
        ``HospitalLetterheadView`` for the dedicated endpoint used by the
        Letterhead Designer, which follows the same fallback rule.
        """
        if obj.letterhead_config:
            return obj.letterhead_config
        return obj.get_default_letterhead_config()


class HospitalUpdateSerializer(serializers.ModelSerializer):
    """Hospital update serializer — tenant_id is never accepted from the client."""

    class Meta:
        model = Hospital
        exclude = ['id', 'tenant_id', 'created_at', 'updated_at']


class HospitalNavStyleSerializer(serializers.ModelSerializer):
    """Dedicated serializer for the tenant-wide nav style preference.

    Used by the ``PATCH /api/hospital/config/nav-style/`` endpoint. Keeping
    this separate from :class:`HospitalUpdateSerializer` lets us return a
    focused, MCP-friendly payload (coded value + human-readable label) without
    exposing every other hospital field on this single-purpose action.
    """
    nav_style_label = serializers.CharField(
        source='get_nav_style_display',
        read_only=True
    )

    class Meta:
        model = Hospital
        fields = ['nav_style', 'nav_style_label']


class HospitalLetterheadSerializer(serializers.Serializer):
    """
    Dedicated read/response serializer for the tenant-wide print letterhead
    configuration, used by ``GET/PATCH /api/hospital/config/letterhead/``.

    Deliberately a plain ``Serializer`` (not a ``ModelSerializer``) because
    ``letterhead_config`` is a single JSONField whose internal shape is a
    structured schema (see ``Hospital.letterhead_config`` docstring in
    ``apps/hospital/models.py``) — validation of that inner shape is done
    explicitly in ``HospitalLetterheadView.patch()`` so we can return
    field-level errors (``text_lines[i].style``, etc.) in the standard
    CLAUDE.md §5 error envelope rather than DRF's default nested-field
    validation errors.

    Response/request body shape (wrapped under the top-level ``"letterhead"``
    key by the view):
        {
          "show_logo": bool,
          "logo_url": str,
          "show_badge": bool,
          "badge_url": str,
          "alignment": "left" | "center",
          "show_hairline": bool,
          "text_lines": [
              {"id": str, "text": str, "style": "title"|"normal",
               "enabled": bool, "order": int},
              ...
          ]
        }
    """
    show_logo = serializers.BooleanField()
    logo_url = serializers.CharField(allow_blank=True)
    show_badge = serializers.BooleanField()
    badge_url = serializers.CharField(allow_blank=True)
    alignment = serializers.ChoiceField(choices=list(Hospital.LETTERHEAD_ALIGNMENTS))
    show_hairline = serializers.BooleanField()
    text_lines = serializers.ListField(child=serializers.DictField())
