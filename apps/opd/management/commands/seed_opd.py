# opd/management/commands/seed_opd.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from datetime import date, time
from decimal import Decimal

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed database with sample OPD data'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write('Starting OPD seeding...')

        # Import models
        from apps.doctors.models import DoctorProfile, Specialty
        from apps.patients.models import PatientProfile
        from apps.appointments.models import Appointment, AppointmentType
        from apps.opd.models import (
            Visit, OPDBill, ProcedureMaster, ClinicalNote, VisitFinding
        )

        # Create groups
        doctor_group, _ = Group.objects.get_or_create(name='Doctor')
        patient_group, _ = Group.objects.get_or_create(name='Patient')

        # Create Specialties
        self.stdout.write('Creating specialties...')
        cardiology, _ = Specialty.objects.get_or_create(
            code='CARD',
            defaults={'name': 'Cardiology', 'is_active': True}
        )
        general, _ = Specialty.objects.get_or_create(
            code='GEN',
            defaults={'name': 'General Medicine', 'is_active': True}
        )

        # Create Doctors
        self.stdout.write('Creating doctors...')
        doctor1_user, created = User.objects.get_or_create(
            username='dr.sharma',
            defaults={
                'email': 'dr.sharma@hospital.com',
                'first_name': 'Rajesh',
                'last_name': 'Sharma',
                'is_active': True,
            }
        )
        if created:
            doctor1_user.set_password('doctor123')
            doctor1_user.save()
            doctor1_user.groups.add(doctor_group)

        doctor2_user, created = User.objects.get_or_create(
            username='dr.patel',
            defaults={
                'email': 'dr.patel@hospital.com',
                'first_name': 'Priya',
                'last_name': 'Patel',
                'is_active': True,
            }
        )
        if created:
            doctor2_user.set_password('doctor123')
            doctor2_user.save()
            doctor2_user.groups.add(doctor_group)

        doctor1, _ = DoctorProfile.objects.get_or_create(
            user=doctor1_user,
            defaults={
                'medical_license_number': 'MH/DOC/12345',
                'consultation_fee': Decimal('800.00'),
                'follow_up_fee': Decimal('400.00'),
                'status': 'active',
            }
        )
        doctor1.specialties.add(cardiology)

        doctor2, _ = DoctorProfile.objects.get_or_create(
            user=doctor2_user,
            defaults={
                'medical_license_number': 'MH/DOC/67890',
                'consultation_fee': Decimal('600.00'),
                'follow_up_fee': Decimal('300.00'),
                'status': 'active',
            }
        )
        doctor2.specialties.add(general)

        # Create Patients
        self.stdout.write('Creating patients...')
        patient1_user, created = User.objects.get_or_create(
            username='patient.singh',
            defaults={
                'email': 'ramesh@email.com',
                'first_name': 'Ramesh',
                'last_name': 'Singh',
                'is_active': True,
            }
        )
        if created:
            patient1_user.set_password('patient123')
            patient1_user.save()
            patient1_user.groups.add(patient_group)

        patient2_user, created = User.objects.get_or_create(
            username='patient.mehta',
            defaults={
                'email': 'sunita@email.com',
                'first_name': 'Sunita',
                'last_name': 'Mehta',
                'is_active': True,
            }
        )
        if created:
            patient2_user.set_password('patient123')
            patient2_user.save()
            patient2_user.groups.add(patient_group)

        patient1, _ = PatientProfile.objects.get_or_create(
            user=patient1_user,
            defaults={
                'first_name': 'Ramesh',
                'last_name': 'Singh',
                'date_of_birth': date(1985, 5, 15),
                'gender': 'male',
                'mobile_primary': '+919876543210',
                'blood_group': 'B+',
                'city': 'Pune',
                'state': 'Maharashtra',
                'status': 'active',
            }
        )

        patient2, _ = PatientProfile.objects.get_or_create(
            user=patient2_user,
            defaults={
                'first_name': 'Sunita',
                'last_name': 'Mehta',
                'date_of_birth': date(1990, 8, 20),
                'gender': 'female',
                'mobile_primary': '+919876543220',
                'blood_group': 'A+',
                'city': 'Pune',
                'state': 'Maharashtra',
                'status': 'active',
            }
        )

        # Create Appointment Type
        self.stdout.write('Creating appointment types...')
        consultation_type, _ = AppointmentType.objects.get_or_create(
            name='Consultation',
            defaults={
                'duration_default': 15,
                'base_consultation_fee': Decimal('500.00')
            }
        )

        # Create Appointments
        self.stdout.write('Creating appointments...')
        today = date.today()

        appt1, _ = Appointment.objects.get_or_create(
            patient=patient1,
            doctor=doctor1,
            appointment_date=today,
            appointment_time=time(10, 0),
            defaults={
                'appointment_type': consultation_type,
                'chief_complaint': 'Chest pain',
                'status': 'confirmed',
                'consultation_fee': doctor1.consultation_fee,
            }
        )

        appt2, _ = Appointment.objects.get_or_create(
            patient=patient2,
            doctor=doctor2,
            appointment_date=today,
            appointment_time=time(11, 0),
            defaults={
                'appointment_type': consultation_type,
                'chief_complaint': 'Fever',
                'status': 'confirmed',
                'consultation_fee': doctor2.consultation_fee,
            }
        )

        # Create Visits
        self.stdout.write('Creating visits...')
        visit1, _ = Visit.objects.get_or_create(
            patient=patient1,
            doctor=doctor1,
            visit_date=today,
            defaults={
                'appointment': appt1,
                'visit_type': 'new',
                'status': 'completed',
            }
        )

        visit2, _ = Visit.objects.get_or_create(
            patient=patient2,
            doctor=doctor2,
            visit_date=today,
            defaults={
                'appointment': appt2,
                'visit_type': 'new',
                'status': 'waiting',
            }
        )

        # Create Procedure Masters
        self.stdout.write('Creating procedure masters...')
        ProcedureMaster.objects.get_or_create(
            code='LAB001',
            defaults={
                'name': 'Complete Blood Count (CBC)',
                'category': 'pathology',
                'default_charge': Decimal('300.00'),
                'is_active': True,
            }
        )

        ProcedureMaster.objects.get_or_create(
            code='RAD001',
            defaults={
                'name': 'Chest X-Ray',
                'category': 'radiology',
                'default_charge': Decimal('500.00'),
                'is_active': True,
            }
        )

        ProcedureMaster.objects.get_or_create(
            code='CARD001',
            defaults={
                'name': 'ECG',
                'category': 'cardiology',
                'default_charge': Decimal('400.00'),
                'is_active': True,
            }
        )

        # Create OPD Bills
        self.stdout.write('Creating OPD bills...')
        OPDBill.objects.get_or_create(
            visit=visit1,
            defaults={
                'doctor': doctor1,
                'opd_type': 'consultation',
                'charge_type': 'first_visit',
                'total_amount': Decimal('800.00'),
                'received_amount': Decimal('800.00'),
                'payment_mode': 'cash',
            }
        )

        # Create Clinical Note
        self.stdout.write('Creating clinical notes...')
        ClinicalNote.objects.get_or_create(
            visit=visit1,
            defaults={
                'present_complaints': 'Chest pain for 2 days',
                'diagnosis': 'Angina pectoris',
                'treatment_plan': 'Medication and rest',
            }
        )

        # Create Visit Finding
        self.stdout.write('Creating visit findings...')
        VisitFinding.objects.get_or_create(
            visit=visit1,
            defaults={
                'finding_type': 'examination',
                'temperature': Decimal('98.4'),
                'pulse': 88,
                'bp_systolic': 140,
                'bp_diastolic': 90,
            }
        )

        self.stdout.write(self.style.SUCCESS('\n✓ OPD seeding complete!'))
        self.stdout.write('\nLogin credentials:')
        self.stdout.write('  Doctors: dr.sharma / dr.patel (password: doctor123)')
        self.stdout.write('  Patients: patient.singh / patient.mehta (password: patient123)')
        self.stdout.write('\nNote: Create Procedure Bills manually from Django Admin')

