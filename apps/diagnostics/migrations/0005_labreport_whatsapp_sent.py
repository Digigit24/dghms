from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diagnostics', '0004_alter_investigation_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='labreport',
            name='whatsapp_sent',
            field=models.BooleanField(default=False),
        ),
    ]
