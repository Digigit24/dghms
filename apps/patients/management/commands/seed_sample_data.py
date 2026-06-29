"""Seed sample data for the Digitech tenant in digihms.

Usage:
    python manage.py seed_sample_data
    python manage.py seed_sample_data --tenant-id <uuid>   # override tenant

Creates (all scoped to Digitech tenant_id):
  - 20 sample PatientProfiles
  - 10 OPD Visits
  - 3 IPD Admissions (requires a Ward + Bed)
  - 5 Prescriptions with items

All data is idempotent: re-running will skip already-created records.
"""

import uuid
import random
from decimal import Decimal
from datetime import date, timedelta

import structlog
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Sample data pools
# ---------------------------------------------------------------------------

FIRST_NAMES_M = ["Arjun", "Rahul", "Suresh", "Vikram", "Manoj", "Deepak", "Anil", "Rajesh", "Sanjay", "Mohit"]
FIRST_NAMES_F = ["Priya", "Sunita", "Anita", "Kavita", "Pooja", "Neha", "Ritu", "Rekha", "Meena", "Geeta"]
LAST_NAMES = ["Sharma", "Verma", "Gupta", "Patel", "Singh", "Kumar", "Joshi", "Agarwal", "Mishra", "Yadav"]
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
CITIES = ["Delhi", "Mumbai", "Jaipur", "Lucknow", "Agra", "Pune", "Indore", "Bhopal", "Kanpur", "Surat"]
DIAGNOSES = [
    "Acute febrile illness",
    "Hypertension",
    "Type 2 Diabetes Mellitus",
    "Upper respiratory tract infection",
    "Gastroenteritis",
    "Migraine",
    "Bronchial asthma",
    "Allergic rhinitis",
    "Chronic back pain",
    "Anxiety disorder",
]
MEDICINES = [
    # (name, dosage, frequency, duration_str, qty)
    ("Paracetamol", "500mg", "TID", "5 days", Decimal("15")),
    ("Amoxicillin", "250mg", "BD", "7 days", Decimal("14")),
    ("Metformin", "500mg", "OD", "30 days", Decimal("30")),
    ("Amlodipine", "5mg", "OD", "30 days", Decimal("30")),
    ("Cetirizine", "10mg", "OD", "10 days", Decimal("10")),
    ("Omeprazole", "20mg", "BD", "14 days", Decimal("28")),
    ("Ibuprofen", "400mg", "TID", "3 days", Decimal("9")),
    ("Azithromycin", "500mg", "OD", "5 days", Decimal("5")),
]

DOCTOR_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")  # placeholder


class Command(BaseCommand):
    help = "Seed 20 patients, 10 OPD visits, 3 IPD admissions, 5 prescriptions for Digitech tenant"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=str,
            default=None,
            help="Override tenant UUID (defaults to DEFAULT_TENANT_ID in settings)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            default=False,
            help="Clear existing seed data before re-seeding",
        )

    def handle(self, *args, **options):
        tenant_id_str = options["tenant_id"] or getattr(settings, "DEFAULT_TENANT_ID", None)
        if not tenant_id_str:
            self.stderr.write(self.style.ERROR(
                "No tenant ID. Set DEFAULT_TENANT_ID in .env or pass --tenant-id."
            ))
            return

        try:
            tenant_id = uuid.UUID(str(tenant_id_str))
        except ValueError:
            self.stderr.write(self.style.ERROR(f"Invalid UUID: {tenant_id_str}"))
            return

        self.stdout.write(f"Seeding data for tenant: {tenant_id}")

        if options["clear"]:
            self._clear_data(tenant_id)

        patients = self._seed_patients(tenant_id)
        visits = self._seed_opd_visits(tenant_id, patients)
        self._seed_ipd_admissions(tenant_id, patients)
        self._seed_prescriptions(tenant_id, visits)

        self.stdout.write(self.style.SUCCESS("Seed complete."))

    # ------------------------------------------------------------------
    def _clear_data(self, tenant_id):
        from apps.patients.models import PatientProfile
        from apps.opd.models import Visit
        from apps.ipd.models import Admission, Ward, Bed
        from apps.pharmacy.models import Prescription, PrescriptionItem

        PrescriptionItem.objects.filter(tenant_id=tenant_id).delete()
        Prescription.objects.filter(tenant_id=tenant_id).delete()
        Admission.objects.filter(tenant_id=tenant_id).delete()
        Bed.objects.filter(tenant_id=tenant_id).delete()
        Ward.objects.filter(tenant_id=tenant_id).delete()
        Visit.objects.filter(tenant_id=tenant_id).delete()
        PatientProfile.objects.filter(tenant_id=tenant_id).delete()
        self.stdout.write("Cleared existing tenant seed data.")

    # ------------------------------------------------------------------
    def _seed_patients(self, tenant_id):
        from apps.patients.models import PatientProfile

        existing = PatientProfile.objects.filter(tenant_id=tenant_id).count()
        if existing >= 20:
            self.stdout.write(f"  Patients: {existing} already exist, skipping.")
            return list(PatientProfile.objects.filter(tenant_id=tenant_id)[:20])

        patients = []
        rng = random.Random(42)  # deterministic

        for i in range(20):
            gender = rng.choice(["male", "female"])
            first = rng.choice(FIRST_NAMES_M if gender == "male" else FIRST_NAMES_F)
            last = rng.choice(LAST_NAMES)
            dob = date.today() - timedelta(days=rng.randint(365 * 18, 365 * 70))
            phone = f"9{rng.randint(100000000, 999999999)}"

            patient, created = PatientProfile.objects.get_or_create(
                tenant_id=tenant_id,
                first_name=first,
                last_name=last,
                date_of_birth=dob,
                defaults={
                    "gender": gender,
                    "phone": phone,
                    "blood_group": rng.choice(BLOOD_GROUPS),
                    "address": f"{rng.randint(1, 999)} Sample Street",
                    "city": rng.choice(CITIES),
                    "state": "Uttar Pradesh",
                },
            )
            if created:
                log.info("seed_patient_created", name=patient.full_name)
            patients.append(patient)

        self.stdout.write(self.style.SUCCESS(f"  Patients: seeded {len(patients)}"))
        return patients

    # ------------------------------------------------------------------
    def _seed_opd_visits(self, tenant_id, patients):
        from apps.opd.models import Visit

        existing = Visit.objects.filter(tenant_id=tenant_id).count()
        if existing >= 10:
            self.stdout.write(f"  OPD Visits: {existing} already exist, skipping.")
            return list(Visit.objects.filter(tenant_id=tenant_id)[:10])

        rng = random.Random(43)
        visits = []
        visit_types = ["new", "follow_up", "emergency"]
        statuses = ["completed", "completed", "completed", "waiting", "in_consultation"]

        for i in range(10):
            patient = patients[i % len(patients)]
            visit_date = date.today() - timedelta(days=rng.randint(0, 30))

            try:
                visit = Visit.objects.create(
                    tenant_id=tenant_id,
                    patient=patient,
                    visit_date=visit_date,
                    visit_type=rng.choice(visit_types),
                    status=rng.choice(statuses),
                    # doctor is nullable FK — leave blank for seed data
                )
                visits.append(visit)
                log.info("seed_visit_created", visit_number=visit.visit_number)
            except Exception as exc:
                log.warning("seed_visit_skip", error=str(exc))

        self.stdout.write(self.style.SUCCESS(f"  OPD Visits: seeded {len(visits)}"))
        return visits

    # ------------------------------------------------------------------
    def _seed_ipd_admissions(self, tenant_id, patients):
        from apps.ipd.models import Ward, Bed, Admission

        existing = Admission.objects.filter(tenant_id=tenant_id).count()
        if existing >= 3:
            self.stdout.write(f"  IPD Admissions: {existing} already exist, skipping.")
            return

        # Ensure a General Ward exists
        ward, _ = Ward.objects.get_or_create(
            tenant_id=tenant_id,
            name="General Ward A",
            defaults={
                "type": "general",
                "floor": "Ground Floor",
                "total_beds": 20,
                "is_active": True,
            },
        )

        rng = random.Random(44)
        created_count = 0

        for i in range(3):
            patient = patients[10 + i]
            bed_number = f"G-{i + 1:02d}"

            bed, _ = Bed.objects.get_or_create(
                tenant_id=tenant_id,
                ward=ward,
                bed_number=bed_number,
                defaults={
                    "bed_type": "general",
                    "daily_charge": 500,
                    "is_occupied": False,
                    "status": "available",
                },
            )

            admission_date = timezone.now() - timedelta(days=rng.randint(1, 10))
            try:
                diagnosis = rng.choice(DIAGNOSES)
                Admission.objects.create(
                    tenant_id=tenant_id,
                    patient=patient,
                    ward=ward,
                    bed=bed,
                    admission_date=admission_date,
                    status="admitted",
                    reason=diagnosis,
                    provisional_diagnosis=diagnosis,
                    doctor_id=DOCTOR_USER_ID,
                )
                created_count += 1
            except Exception as exc:
                log.warning("seed_admission_skip", error=str(exc))

        self.stdout.write(self.style.SUCCESS(f"  IPD Admissions: seeded {created_count}"))

    # ------------------------------------------------------------------
    def _seed_prescriptions(self, tenant_id, visits):
        from apps.pharmacy.models import Prescription, PrescriptionItem

        existing = Prescription.objects.filter(tenant_id=tenant_id).count()
        if existing >= 5:
            self.stdout.write(f"  Prescriptions: {existing} already exist, skipping.")
            return

        if not visits:
            self.stdout.write("  No visits to attach prescriptions to, skipping.")
            return

        rng = random.Random(45)
        created_count = 0

        for i in range(min(5, len(visits))):
            visit = visits[i]
            rx = Prescription.objects.create(
                tenant_id=tenant_id,
                visit=visit,
                status="pending",
                created_by_user_id=DOCTOR_USER_ID,
            )

            for j in range(rng.randint(1, 3)):
                med = rng.choice(MEDICINES)
                PrescriptionItem.objects.create(
                    tenant_id=tenant_id,
                    prescription=rx,
                    medicine_name=med[0],
                    dosage=med[1],
                    frequency=med[2],
                    duration=med[3],
                    quantity=med[4],
                    is_dispensed=False,
                )

            created_count += 1
            log.info("seed_prescription_created", prescription_id=rx.id, visit_id=visit.id)

        self.stdout.write(self.style.SUCCESS(f"  Prescriptions: seeded {created_count}"))
