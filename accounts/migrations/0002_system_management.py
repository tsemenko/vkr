from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='ADGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='Название AD-группы')),
                ('distinguished_name', models.CharField(blank=True, max_length=255, verbose_name='DN группы')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'AD-группа',
                'verbose_name_plural': 'AD-группы',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='OrganizationalUnit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='Название OU')),
                ('distinguished_name', models.CharField(max_length=255, unique=True, verbose_name='DN OU')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активно')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Организационная единица',
                'verbose_name_plural': 'Организационные единицы',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='SettingsChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('create', 'Создание'), ('update', 'Изменение'), ('delete', 'Удаление'), ('assign', 'Назначение'), ('validate', 'Проверка')], max_length=20, verbose_name='Действие')),
                ('object_type', models.CharField(max_length=120, verbose_name='Сущность')),
                ('object_name', models.CharField(max_length=255, verbose_name='Объект')),
                ('details', models.JSONField(blank=True, default=dict, verbose_name='Изменения')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='settings_changes', to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'verbose_name': 'Журнал изменений настроек',
                'verbose_name_plural': 'Журнал изменений настроек',
                'ordering': ['-created_at'],
                'permissions': [('create_ad_accounts', 'Создание учётных записей'), ('rename_ad_accounts', 'Переименование учётных записей'), ('view_action_logs', 'Просмотр журнала действий'), ('view_ad_monitoring', 'Просмотр мониторинга AD'), ('unlock_ad_accounts', 'Разблокировка пользователей AD'), ('manage_system_settings', 'Управление системой'), ('manage_directory', 'Управление справочниками'), ('manage_access_roles', 'Управление ролями доступа'), ('view_settings_change_log', 'Просмотр журнала изменений настроек')],
            },
        ),
        migrations.CreateModel(
            name='BranchDirectory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='Код филиала')),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='Название филиала')),
                ('is_head_office', models.BooleanField(default=False, verbose_name='Головной вуз')),
                ('profile_path', models.CharField(blank=True, max_length=255, verbose_name='Путь к профилю')),
                ('home_directory', models.CharField(blank=True, max_length=255, verbose_name='Путь к домашней папке')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
                ('sort_order', models.PositiveIntegerField(default=100, verbose_name='Порядок сортировки')),
                ('notes', models.TextField(blank=True, verbose_name='Примечание')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ou', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='branches', to='accounts.organizationalunit', verbose_name='OU для учётных записей')),
            ],
            options={
                'verbose_name': 'Филиал',
                'verbose_name_plural': 'Филиалы',
                'ordering': ['sort_order', 'code', 'name'],
            },
        ),
        migrations.AddField(
            model_name='branchdirectory',
            name='default_groups',
            field=models.ManyToManyField(blank=True, related_name='default_branches', to='accounts.adgroup', verbose_name='Группы по умолчанию'),
        ),
        migrations.AddField(
            model_name='branchdirectory',
            name='female_groups',
            field=models.ManyToManyField(blank=True, related_name='female_branches', to='accounts.adgroup', verbose_name='Доп. группы для женщин'),
        ),
    ]
