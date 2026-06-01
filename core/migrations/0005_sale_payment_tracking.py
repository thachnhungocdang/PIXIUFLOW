from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_purchase_payment_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='payment_method',
            field=models.CharField(
                choices=[
                    ('cash', 'Tiền mặt'),
                    ('transfer', 'Chuyển khoản'),
                    ('debt', 'Nợ/chưa thanh toán'),
                ],
                default='cash',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='payment_due_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
