# Generated migration

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('opd', '0004_alter_opdbill_charge_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='visit',
            name='visit_date',
            field=models.DateField(default=django.utils.timezone.now),
        ),
    ]
