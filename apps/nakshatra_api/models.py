# apps/nakshatra_api/models.py

from django.db import models


class NakshatraLead(models.Model):
    """
    Stores lead information from Nakshatra form submissions.

    This model stores all leads that come through the Nakshatra API endpoint.
    No tenant_id or user_id required as this is a public endpoint.
    """

    # Lead Information
    first_name = models.CharField(
        max_length=100,
        help_text="First name of the lead"
    )
    last_name = models.CharField(
        max_length=100,
        help_text="Last name of the lead"
    )
    email = models.EmailField(
        max_length=255,
        help_text="Email address of the lead"
    )
    phone = models.CharField(
        max_length=20,
        help_text="Phone number of the lead"
    )
    services = models.CharField(
        max_length=255,
        help_text="Service type requested by the lead"
    )
    appointment_date = models.CharField(
        max_length=100,
        help_text="Appointment or inquiry date"
    )

    # Tracking Information
    client_event_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Client-side event ID for Meta tracking deduplication"
    )

    # Request Metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the requester"
    )
    user_agent = models.TextField(
        null=True,
        blank=True,
        help_text="User agent string from the request"
    )

    # Integration Status
    custom_api_status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('failed', 'Failed'),
            ('pending', 'Pending'),
            ('error', 'Error'),
        ],
        default='pending',
        help_text="Status of custom API submission"
    )
    custom_api_response = models.TextField(
        null=True,
        blank=True,
        help_text="Response from custom API"
    )

    meta_capi_status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('failed', 'Failed'),
            ('pending', 'Pending'),
            ('error', 'Error'),
        ],
        default='pending',
        help_text="Status of Meta CAPI submission"
    )
    meta_capi_response = models.TextField(
        null=True,
        blank=True,
        help_text="Response from Meta CAPI"
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the lead was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the lead was last updated"
    )

    class Meta:
        db_table = 'nakshatra_leads'
        ordering = ['-created_at']
        verbose_name = 'Nakshatra Lead'
        verbose_name_plural = 'Nakshatra Leads'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
            models.Index(fields=['custom_api_status']),
            models.Index(fields=['meta_capi_status']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.email}"

    @property
    def full_name(self):
        """Returns the full name of the lead"""
        return f"{self.first_name} {self.last_name}"

    @property
    def is_successfully_processed(self):
        """Returns True if both custom API and Meta CAPI were successful"""
        return (
            self.custom_api_status == 'success' and
            self.meta_capi_status == 'success'
        )
