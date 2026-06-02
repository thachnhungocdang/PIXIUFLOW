from decimal import Decimal

from django.db import migrations, models


def backfill_sale_cogs(apps, schema_editor):
    Sale = apps.get_model('core', 'Sale')
    for sale in Sale.objects.select_related('product').filter(cogs_amount=0):
        sale.cogs_amount = (sale.product.price_buy_latest or Decimal('0')) * sale.quantity
        sale.save(update_fields=['cogs_amount'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_expense_payment_date_purchase_payment_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='cogs_amount',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Gia von tai thoi diem ban, tinh tu price_buy_latest cua san pham', max_digits=15),
        ),
        migrations.RunPython(backfill_sale_cogs, migrations.RunPython.noop),
    ]
