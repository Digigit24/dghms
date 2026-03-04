"""
Migration: add specimen_type, reported_by to Investigation;
           expand CATEGORY_CHOICES; make code blank=True.
"""
import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diagnostics', '0002_initial'),
    ]

    operations = [
        # New fields
        migrations.AddField(
            model_name='investigation',
            name='specimen_type',
            field=models.CharField(
                blank=True,
                max_length=100,
                help_text='Type of specimen required (e.g., Blood, Urine, Stool, Sputum)',
            ),
        ),
        migrations.AddField(
            model_name='investigation',
            name='reported_by',
            field=models.CharField(
                blank=True,
                max_length=100,
                help_text='Who typically reports this test (e.g., Pathologist, Radiologist)',
            ),
        ),
        # Allow code to be blank (auto-generated)
        migrations.AlterField(
            model_name='investigation',
            name='code',
            field=models.CharField(
                blank=True,
                max_length=50,
                help_text='Unique test code (e.g., CBC, CXR). Auto-generated if left blank.',
            ),
        ),
        # Expanded category choices
        migrations.AlterField(
            model_name='investigation',
            name='category',
            field=models.CharField(
                choices=[
                    ('haematology', 'Haematology'),
                    ('clinical_chemistry', 'Clinical Chemistry'),
                    ('biochemistry', 'Biochemistry'),
                    ('microbiology', 'Microbiology'),
                    ('serology', 'Serology'),
                    ('immunology', 'Immunology'),
                    ('histopathology', 'Histopathology'),
                    ('cytology', 'Cytology'),
                    ('genetics', 'Genetics'),
                    ('molecular_biology', 'Molecular Biology'),
                    ('blood_bank', 'Blood Bank'),
                    ('toxicology', 'Toxicology'),
                    ('endocrinology', 'Endocrinology'),
                    ('radiology', 'Radiology'),
                    ('ultrasound', 'Ultrasound'),
                    ('ct_scan', 'CT Scan'),
                    ('mri', 'MRI'),
                    ('xray', 'X-Ray'),
                    ('ecg', 'ECG'),
                    ('cardiology', 'Cardiology'),
                    ('pathology', 'Pathology'),
                    ('laboratory', 'Laboratory'),
                    ('other', 'Other'),
                ],
                default='laboratory',
                max_length=50,
            ),
        ),
    ]
