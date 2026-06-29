import datetime
import uuid
import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_alter_paymentcategory_unique_per_tenant'),
        ('opd', '0001_initial'),
        ('ipd', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BillPayment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tenant_id', models.UUIDField(db_index=True)),
                ('bill_type', models.CharField(choices=[('opd', 'OPD'), ('ipd', 'IPD')], max_length=10)),
                ('opd_bill', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='bill_payments',
                    to='opd.opdbill',
                )),
                ('ipd_bill', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='bill_payments',
                    to='ipd.ipdbilling',
                )),
                ('bill_number', models.CharField(blank=True, max_length=60)),
                ('patient_name', models.CharField(blank=True, max_length=255)),
                ('encounter_number', models.CharField(
                    blank=True,
                    help_text='Visit number (OPD) or Admission ID (IPD)',
                    max_length=100,
                )),
                ('amount', models.DecimalField(
                    decimal_places=2, max_digits=10,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                )),
                ('payment_mode', models.CharField(
                    choices=[
                        ('cash', 'Cash'), ('card', 'Card'), ('upi', 'UPI'),
                        ('bank', 'Bank Transfer'), ('insurance', 'Insurance'),
                        ('cheque', 'Cheque'), ('razorpay', 'Razorpay'),
                        ('multiple', 'Multiple'), ('other', 'Other'),
                    ],
                    default='cash', max_length=20,
                )),
                ('payment_date', models.DateField(default=datetime.date.today)),
                ('notes', models.TextField(blank=True)),
                ('recorded_by_user_id', models.UUIDField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Bill Payment',
                'verbose_name_plural': 'Bill Payments',
                'db_table': 'bill_payments',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='billpayment',
            index=models.Index(fields=['tenant_id'], name='billpay_tenant_idx'),
        ),
        migrations.AddIndex(
            model_name='billpayment',
            index=models.Index(fields=['tenant_id', 'bill_type'], name='billpay_tenant_type_idx'),
        ),
        migrations.AddIndex(
            model_name='billpayment',
            index=models.Index(fields=['tenant_id', 'payment_date'], name='billpay_tenant_date_idx'),
        ),
        migrations.AddIndex(
            model_name='billpayment',
            index=models.Index(fields=['tenant_id', 'payment_mode'], name='billpay_tenant_mode_idx'),
        ),
        migrations.AddIndex(
            model_name='billpayment',
            index=models.Index(fields=['opd_bill'], name='billpay_opd_bill_idx'),
        ),
        migrations.AddIndex(
            model_name='billpayment',
            index=models.Index(fields=['ipd_bill'], name='billpay_ipd_bill_idx'),
        ),
    ]
