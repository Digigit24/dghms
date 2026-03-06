from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diagnostics', '0005_labreport_whatsapp_sent'),
    ]

    operations = [
        migrations.AddField(
            model_name='labreport',
            name='whatsapp_message_log_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='labreport',
            name='whatsapp_read',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='labreport',
            name='whatsapp_failed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='labreport',
            name='whatsapp_delivered',
            field=models.BooleanField(default=False),
        ),
    ]
