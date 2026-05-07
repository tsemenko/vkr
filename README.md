# Веб-сервис AD

Проект реализует веб-интерфейс для создания учетных записей Active Directory, просмотра мониторинга AD, ведения журнала действий и управления справочниками системы.

## Основная навигация

После авторизации пользователь попадает в раздел **Мониторинг**.

Из мониторинга доступны основные разделы:
- **Создание учетной записи**;
- **Журнал действий**;
- **Управление системой**.

Из журнала действий можно перейти в раздел **Ошибки**.

В разделе **Управление системой** доступны:
- **Филиалы**;
- **AD-группы**;
- **Правила по умолчанию**;
- **Роли**;
- **Доступ пользователей**;
- **Создание пользователя**.

## Состав проекта

- `adweb/` — настройки Django-проекта, маршруты, Celery-приложение.
- `accounts/` — основное приложение веб-сервиса.
- `accounts/services/` — сервисная логика для WinRM, PowerShell, AD и мониторинга.
- `accounts/management/commands/` — служебные команды для первичной настройки и обновления мониторинга.
- `templates/` — HTML-шаблоны интерфейса.
- `static/` — статические файлы проекта.
- `deploy/systemd/` — примеры systemd-сервисов для Django, Celery worker и Celery beat.

## Быстрый запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py bootstrap_web_roles
python manage.py bootstrap_directory_config
python manage.py runserver 0.0.0.0:8000
```

Для Windows вместо `source .venv/bin/activate` используется:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Первичная настройка доступа

Базовые группы веб-интерфейса:
- `AD Admins` — журнал действий и ошибки;
- `AD Super Admins` — управление системой.

Создать или обновить пользователя веб-интерфейса можно командой:

```bash
python manage.py provision_web_user admts --groups "AD Super Admins" --staff
```

## Проверка проекта
```bash
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py test
```

## Важные замечания

Файл `.env` не входит в архив и не должен попадать в репозиторий. Для настройки используется `.env.example`.

Локальная база `db.sqlite3`, `__pycache__` и файлы `celerybeat-schedule*` не входят в итоговый архив, потому что это локальные артефакты запуска.
