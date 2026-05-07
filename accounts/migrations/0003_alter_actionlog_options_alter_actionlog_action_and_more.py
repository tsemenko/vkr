
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_system_management'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='actionlog',
            options={'ordering': ['-created_at'], 'verbose_name': 'Журнал действий', 'verbose_name_plural': 'Журнал действий'},
        ),
        migrations.AlterField(
            model_name='actionlog',
            name='action',
            field=models.CharField(max_length=64, verbose_name='Действие'),
        ),
        migrations.AlterField(
            model_name='actionlog',
            name='actor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Пользователь'),
        ),
        migrations.AlterField(
            model_name='actionlog',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='Создано'),
        ),
        migrations.AlterField(
            model_name='actionlog',
            name='details',
            field=models.TextField(blank=True, default='', verbose_name='Детали'),
        ),
        migrations.AlterField(
            model_name='actionlog',
            name='success',
            field=models.BooleanField(default=False, verbose_name='Успешно'),
        ),
        migrations.AlterField(
            model_name='actionlog',
            name='target_login',
            field=models.CharField(blank=True, default='', max_length=128, verbose_name='Логин'),
        ),
    ]
