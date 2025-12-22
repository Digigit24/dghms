# Generated migration - Make appointment_type optional

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(

            
            model_name='appointment',
            name='appointment_type',
            field=models.ForeignKey(
                blank=True,
                help_text='Type of appointment (optional)',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='appointments',
                to='appointments.appointmenttype'
            ),
        ),
    ]
