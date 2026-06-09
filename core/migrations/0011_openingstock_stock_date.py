from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_category_user_expense_user_openingstock_user_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='openingstock',
            name='stock_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
