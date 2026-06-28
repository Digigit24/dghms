from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('opd', '0007_add_visit_followup_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='priority',
            field=models.CharField(
                choices=[
                    ('low', 'Low'),
                    ('normal', 'Normal'),
                    ('high', 'High'),
                    ('urgent', 'Urgent'),
                ],
                default='normal',
                db_index=True,
                max_length=16,
                help_text='Visit priority: low, normal, high, urgent',
            ),
        ),
        migrations.AlterField(
            model_name='visit',
            name='visit_type',
            field=models.CharField(
                choices=[
                    ('new', 'New Visit'),
                    ('follow_up', 'Follow-up'),
                    ('emergency', 'Emergency'),
                    ('referral', 'Referral'),
                ],
                default='new',
                max_length=20,
            ),
        ),
    ]
