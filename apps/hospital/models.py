from django.db import models
from django.core.exceptions import ValidationError


class Hospital(models.Model):
    """
    Hospital/Clinic configuration - Singleton model.
    Only one instance allowed in the entire system.
    """
    TYPE_CHOICES = [
        ('clinic', 'Clinic'),
        ('hospital', 'Hospital'),
    ]

    # --- Letterhead config enums (used by Hospital.letterhead_config schema
    # validation in apps/hospital/views.py::HospitalLetterheadView) ----------
    LETTERHEAD_TEXT_STYLES = ('title', 'normal')
    LETTERHEAD_ALIGNMENTS = ('left', 'center')

    # Tenant
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    # Basic Information
    name = models.CharField(max_length=200)
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='hospital'
    )
    tagline = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        help_text="Brief tagline or slogan"
    )

    # Contact Information
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    alternate_phone = models.CharField(max_length=15, blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    # Address
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    pincode = models.CharField(max_length=10)

    # Media - temporarily disabled ImageField
    logo = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Logo URL (ImageField disabled temporarily)"
    )

    # Settings
    working_hours = models.CharField(
        max_length=100,
        default='24/7',
        help_text="e.g., '9 AM - 9 PM' or '24/7'"
    )
    has_emergency = models.BooleanField(
        default=True,
        help_text="Has emergency services"
    )
    has_pharmacy = models.BooleanField(
        default=True,
        help_text="Has in-house pharmacy"
    )
    has_laboratory = models.BooleanField(
        default=True,
        help_text="Has in-house laboratory"
    )

    # Additional
    registration_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Hospital registration number"
    )
    established_date = models.DateField(blank=True, null=True)

    # --- Patient ID (UHID) generation config -----------------------------
    # NEW (2026): per-tenant custom UHID prefix/format. Fed from the
    # admin.celiyo.com tenant-config JSON (or edited here). Defaults reproduce
    # the legacy "PAT{year}NNNN" scheme so existing behaviour is unchanged.
    patient_id_prefix = models.CharField(
        max_length=10,
        default='PAT',
        help_text="UHID prefix, e.g. 'UHID' or 'PAT'."
    )
    patient_id_include_year = models.BooleanField(
        default=True,
        help_text="Include the 4-digit year after the prefix (e.g. PAT2026...)."
    )
    patient_id_padding = models.PositiveSmallIntegerField(
        default=4,
        help_text="Zero-padding width for the running number (e.g. 6 -> UHID000123)."
    )

    # --- UI preference ------------------------------------------------------
    # Tenant-wide (shared across all users of this tenant) — which navigation
    # layout the frontend should render: horizontal top nav or vertical sidebar.
    nav_style = models.CharField(
        max_length=10,
        choices=[("horizontal", "Horizontal"), ("vertical", "Vertical")],
        default="horizontal",
        help_text="Tenant-wide preference: horizontal top nav vs vertical sidebar",
    )

    # --- Print letterhead (Letterhead Designer) ------------------------------
    # Tenant-configurable print letterhead layout used to render the header
    # block (logo, accreditation badge, hospital text lines, hairline rule)
    # on every printed clinical/IPD form. Empty ``{}`` means "not configured
    # yet" — callers should use ``get_default_letterhead_config()`` (or the
    # serializer's read-time fallback) to compute a sensible default seeded
    # from the existing Hospital fields below.
    #
    # JSON schema:
    # {
    #   "show_logo": bool,
    #   "logo_url": str,                # falls back to Hospital.logo
    #   "show_badge": bool,              # no source field yet -> defaults False
    #   "badge_url": str,                # no source field yet -> defaults ""
    #   "alignment": "left" | "center",
    #   "show_hairline": bool,
    #   "text_lines": [
    #       {
    #           "id": str,               # stable per-line slug (React key / DnD identity)
    #           "text": str,
    #           "style": "title" | "normal",
    #           "enabled": bool,
    #           "order": int,
    #       },
    #       ...
    #   ],
    # }
    letterhead_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tenant-configurable print letterhead layout (logo, badge, text lines, alignment)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hospital_config'
        verbose_name = 'Hospital Configuration'
        verbose_name_plural = 'Hospital Configuration'
        indexes = [
            models.Index(fields=['tenant_id']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        """Enforce singleton pattern - only one hospital allowed"""
        if not self.pk and Hospital.objects.exists():
            raise ValidationError(
                'Hospital configuration already exists. '
                'Please update the existing record instead of creating a new one.'
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of hospital configuration"""
        raise ValidationError(
            'Hospital configuration cannot be deleted. '
            'Please update it instead.'
        )

    @classmethod
    def get_hospital(cls):
        """Get the hospital instance (singleton)"""
        hospital = cls.objects.first()
        if not hospital:
            raise ValidationError(
                'Hospital configuration not found. '
                'Please create one via Django admin.'
            )
        return hospital

    @property
    def full_address(self):
        """Returns formatted full address"""
        return f"{self.address}, {self.city}, {self.state} {self.pincode}, {self.country}"

    def get_default_letterhead_config(self) -> dict:
        """
        Build a sensible starting ``letterhead_config`` from this hospital's
        existing fields, so every tenant gets a working printed letterhead on
        day one without configuring anything in the Letterhead Designer.

        Mirrors the layout of a typical real-world hospital letterhead:
        bold hospital name on its own line, then the full address, then
        email, then phone number(s) + registration number on one line.

        Source field -> text line mapping:
          - "name"    <- self.name                              (style: title)
          - "address" <- self.address + city + state + pincode  (style: normal)
          - "email"   <- self.email (prefixed "E-mail : ")      (style: normal)
          - "contact" <- phone[/alternate_phone] + "REG. No. : {registration_number}"
                                                                 (style: normal)

        ``show_badge``/``badge_url`` default to False/"" since Hospital has
        no existing accreditation-badge field to seed from.
        """
        address_parts = [
            part.strip()
            for part in [self.address, self.city, self.state, self.pincode]
            if part and str(part).strip()
        ]
        full_address_line = ", ".join(address_parts)

        phones = [p.strip() for p in [self.phone, self.alternate_phone] if p and p.strip()]
        phone_part = " / ".join(phones)
        reg_part = f"REG. No. : {self.registration_number}" if self.registration_number else ""
        contact_bits = [bit for bit in [phone_part, reg_part] if bit]
        contact_line = "   ".join(contact_bits)

        text_lines = [
            {
                "id": "name",
                "text": self.name or "",
                "style": "title",
                "enabled": True,
                "order": 0,
            },
            {
                "id": "address",
                "text": full_address_line,
                "style": "normal",
                "enabled": True,
                "order": 1,
            },
            {
                "id": "email",
                "text": f"E-mail : {self.email}" if self.email else "",
                "style": "normal",
                "enabled": True,
                "order": 2,
            },
            {
                "id": "contact",
                "text": contact_line,
                "style": "normal",
                "enabled": True,
                "order": 3,
            },
        ]

        return {
            "show_logo": bool(self.logo),
            "logo_url": self.logo or "",
            "show_badge": False,
            "badge_url": "",
            "alignment": "left",
            "show_hairline": True,
            "text_lines": text_lines,
        }

