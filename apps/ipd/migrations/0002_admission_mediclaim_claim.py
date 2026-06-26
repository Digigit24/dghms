from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ipd', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='admission',
            name='claim_notes',
            field=models.TextField(blank=True, help_text='Manual notes for claim processing'),
        ),
        migrations.AddField(
            model_name='admission',
            name='claim_reference_number',
            field=models.CharField(blank=True, help_text='TPA claim/pre-auth/reference number', max_length=100),
        ),
        migrations.AddField(
            model_name='admission',
            name='claim_status',
            field=models.CharField(choices=[('not_applicable', 'Not Applicable'), ('not_started', 'Not Started'), ('documents_pending', 'Documents Pending'), ('submitted', 'Submitted'), ('under_review', 'Under Review'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('settled', 'Settled')], default='not_applicable', help_text='Manual claim processing status', max_length=30),
        ),
        migrations.AddField(
            model_name='admission',
            name='has_mediclaim',
            field=models.BooleanField(default=False, help_text='Whether the patient has Mediclaim/TPA coverage for this admission'),
        ),
        migrations.AddField(
            model_name='admission',
            name='tpa_name',
            field=models.CharField(blank=True, help_text='Selected or entered TPA/insurance provider name', max_length=200),
        ),
        migrations.AddIndex(
            model_name='admission',
            index=models.Index(fields=['tenant_id', 'has_mediclaim'], name='ipd_admissi_tenant__690689_idx'),
        ),
        migrations.AddIndex(
            model_name='admission',
            index=models.Index(fields=['tenant_id', 'claim_status'], name='ipd_admissi_tenant__7670cf_idx'),
        ),
    ]
