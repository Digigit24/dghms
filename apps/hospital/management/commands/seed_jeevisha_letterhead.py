from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.hospital.models import Hospital
from apps.hospital.views import _validate_letterhead_config


JEEVISHA_TENANT_ID = UUID("615da126-a7d8-4112-a5ae-45bca4c623b6")

JEEVISHA_LETTERHEAD = {
    "show_logo": False,
    "logo_url": "",
    "show_badge": False,
    "badge_url": "",
    "alignment": "left",
    "show_hairline": False,
    "layout_mode": "two_column",
    "text_lines": [
        {
            "id": "hospital-name",
            "text": "JEEVISHA",
            "style": "title",
            "enabled": True,
            "order": 0,
        },
        {
            "id": "hospital-specialities",
            "text": "SPINE | PAIN | REGENERATIVE HOSPITAL",
            "style": "normal",
            "enabled": True,
            "order": 1,
        },
    ],
    "right_column_lines": [
        {
            "id": "doctor-name",
            "text": "Dr. SANJOG MEKEWAR",
            "style": "title",
            "enabled": True,
            "order": 0,
        },
        {
            "id": "doctor-credentials",
            "text": "MBBS DA DNB FIPM FIAPM",
            "style": "normal",
            "enabled": True,
            "order": 1,
        },
        {
            "id": "doctor-role",
            "text": "CONSULTANT PAIN PHYSICIAN",
            "style": "normal",
            "enabled": True,
            "order": 2,
        },
        {
            "id": "doctor-registration",
            "text": "Reg no: 2011/09/2971",
            "style": "normal",
            "enabled": True,
            "order": 3,
        },
    ],
    "background_pattern_url": None,
    "info_bar": {
        "enabled": True,
        "background_color": "#1e3a5f",
        "text_color": "#ffffff",
        "lines": [
            {
                "id": "address",
                "text": "Shop No: 214, Second Floor, Solitaire Business Hub, Wakad, Pune: 411057",
                "align": "center",
            },
            {
                "id": "contact",
                "text": "Ph : 911-9111-837    Website : www.jeevishapainclinic.com",
                "align": "center",
            },
        ],
    },
}


class Command(BaseCommand):
    help = "Idempotently seed the Jeevisha tenant's print letterhead."

    def handle(self, *args, **options):
        cleaned, error = _validate_letterhead_config(JEEVISHA_LETTERHEAD)
        if error:
            raise CommandError(f"Bundled letterhead is invalid: {error['message']}")

        hospital = Hospital.objects.filter(tenant_id=JEEVISHA_TENANT_ID).first()
        if hospital is None:
            raise CommandError(
                f"No Hospital configuration exists for tenant {JEEVISHA_TENANT_ID}; "
                "refusing to create an incomplete hospital row."
            )

        if hospital.letterhead_config == cleaned:
            self.stdout.write(self.style.SUCCESS("Jeevisha letterhead is already up to date."))
            return

        hospital.letterhead_config = cleaned
        hospital.save(update_fields=["letterhead_config", "updated_at"])
        self.stdout.write(self.style.SUCCESS("Jeevisha letterhead seeded successfully."))
