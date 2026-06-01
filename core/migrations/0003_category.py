from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_openingstock'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('path', models.CharField(max_length=255, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('note', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['path'],
            },
        ),
    ]
