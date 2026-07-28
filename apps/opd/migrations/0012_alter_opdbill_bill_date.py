from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    """Make OPDBill.bill_date an editable field.

    Changes bill_date from auto_now_add=True (immutable, set once at insert)
    to default=timezone.now (auto-filled on create but editable afterwards),
    so the billing UI can correct the printed bill date. This is a Django
    metadata-only change: bill_date stays a `timestamp with time zone` column
    and timezone.now is a Python-level default (no DB default), so this
    migration emits no data-altering SQL.
    """

    dependencies = [
        ('opd', '0011_create_service'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opdbill',
            name='bill_date',
            field=models.DateTimeField(
                default=django.utils.timezone.now,
                db_index=True,
                help_text='Bill date shown on the printed bill (editable).',
            ),
        ),
    ]
