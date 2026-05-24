# Продакшен-развертывание adweb

Эта инструкция описывает подготовку проекта к запуску на Linux-сервере с Nginx, Gunicorn, PostgreSQL, Redis и Celery.

## Целевая схема

```text
Пользователь
  |
  v
Nginx :80/:443
  |
  v
Gunicorn unix:/run/adweb/gunicorn.sock
  |
  v
Django adweb
  |
  +-- PostgreSQL
  +-- Redis
  +-- Celery worker
  +-- Celery beat
  +-- AD через WinRM
```


## Что уже подготовлено в проекте

- `requirements-prod.txt` — зависимости для production.
- `.env.production.example` — пример production-переменных.
- `STATIC_ROOT = BASE_DIR / "staticfiles"` — каталог для `collectstatic`.
- `DATABASE_URL` — подключение PostgreSQL через переменную окружения.
- `deploy/systemd/gunicorn.service.example` — пример systemd-службы Gunicorn.
- `deploy/systemd/celery-worker.service.example` — пример службы Celery worker.
- `deploy/systemd/celery-beat.service.example` — пример службы Celery beat.
- `deploy/nginx/adweb.conf.example` — пример Nginx-конфига.

## Подготовка сервера

Пример для Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip nginx postgresql postgresql-contrib redis-server
```

Проверь доступность AD с Linux-сервера

## PostgreSQL

Создай базу и пользователя:

```bash
sudo -u postgres psql
```

Внутри `psql`:

```sql
CREATE DATABASE adweb;
CREATE USER adweb_user WITH PASSWORD 'change-me';
ALTER ROLE adweb_user SET client_encoding TO 'utf8';
ALTER ROLE adweb_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE adweb_user SET timezone TO 'Europe/Moscow';
GRANT ALL PRIVILEGES ON DATABASE adweb TO adweb_user;
\q
```

Если PostgreSQL 15 и выше, дополнительно:

```bash
sudo -u postgres psql -d adweb -c "GRANT ALL ON SCHEMA public TO adweb_user;"
```

## Python-окружение

```bash
cd /opt/adweb
sudo -u adweb python3.11 -m venv .venv
sudo -u adweb /opt/adweb/.venv/bin/python -m pip install --upgrade pip
sudo -u adweb /opt/adweb/.venv/bin/python -m pip install -r requirements-prod.txt
```

## Production `.env`

Создай файл:

```bash
sudo -u adweb cp /opt/adweb/.env.production.example /opt/adweb/.env
sudo -u adweb nano /opt/adweb/.env
```

Обязательно поменяй:

```env
SECRET_KEY=длинный_случайный_ключ
DEBUG=0
ALLOWED_HOSTS=домен_или_ip_сервера
CSRF_TRUSTED_ORIGINS=https://домен_или_ip_сервера

DATABASE_URL=postgres://adweb_user:пароль@127.0.0.1:5432/adweb

REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1

DC_HOST=192.168.56.10
DC_WINRM_USER=LAB\svc.account.creator
DC_WINRM_PASSWORD=пароль
```

Если HTTPS уже настроен в Nginx, включи:

```env
SECURE_SSL_REDIRECT=1
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
USE_X_FORWARDED_PROTO=1
```

HSTS включай только после проверки HTTPS:

```env
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=1
SECURE_HSTS_PRELOAD=1
```

## Миграции и статические файлы

```bash
cd /opt/adweb
sudo -u adweb /opt/adweb/.venv/bin/python manage.py check
sudo -u adweb /opt/adweb/.venv/bin/python manage.py migrate
sudo -u adweb /opt/adweb/.venv/bin/python manage.py collectstatic --noinput
sudo -u adweb /opt/adweb/.venv/bin/python manage.py bootstrap_web_roles
sudo -u adweb /opt/adweb/.venv/bin/python manage.py bootstrap_directory_config
```

Создай администратора веб-интерфейса:

```bash
sudo -u adweb /opt/adweb/.venv/bin/python manage.py provision_web_user admts --groups "AD Super Admins" --staff
```

## Gunicorn systemd

Скопируй пример:

```bash
sudo cp /opt/adweb/deploy/systemd/gunicorn.service.example /etc/systemd/system/adweb-gunicorn.service
sudo systemctl daemon-reload
sudo systemctl enable --now adweb-gunicorn
```

Проверка:

```bash
systemctl status adweb-gunicorn
```

Сокет должен появиться здесь:

```text
/run/adweb/gunicorn.sock
```

## Nginx

Скопируй конфиг:

```bash
sudo cp /opt/adweb/deploy/nginx/adweb.conf.example /etc/nginx/sites-available/adweb
sudo ln -s /etc/nginx/sites-available/adweb /etc/nginx/sites-enabled/adweb
```

В файле `/etc/nginx/sites-available/adweb` поменяй:

```nginx
server_name adweb.example.local ;
```

на свой домен или IP.

Проверка и перезапуск:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Celery

```bash
sudo cp /opt/adweb/deploy/systemd/celery-worker.service.example /etc/systemd/system/adweb-celery-worker.service
sudo cp /opt/adweb/deploy/systemd/celery-beat.service.example /etc/systemd/system/adweb-celery-beat.service
sudo systemctl daemon-reload
sudo systemctl enable --now adweb-celery-worker adweb-celery-beat
```

Проверка:

```bash
systemctl status adweb-celery-worker
systemctl status adweb-celery-beat
cd /opt/adweb
sudo -u adweb /opt/adweb/.venv/bin/celery -A adweb inspect ping
```

Ожидаемый результат:

```text
pong
```

## Проверка production

```bash
cd /opt/adweb
sudo -u adweb /opt/adweb/.venv/bin/python manage.py check --deploy
sudo -u adweb /opt/adweb/.venv/bin/python manage.py test
sudo -u adweb /opt/adweb/.venv/bin/python manage.py refresh_ad_snapshot
```

Проверка Redis:

```bash
redis-cli ping
```

Ожидаемый результат:

```text
PONG
```

Проверка сайта:

```bash
curl -I http://127.0.0.1/
```

## Что менять при переносе на другой сервер

В `.env` меняются:

- `SECRET_KEY`;
- `ALLOWED_HOSTS`;
- `CSRF_TRUSTED_ORIGINS`;
- `DATABASE_URL`;
- `REDIS_URL`;
- `CELERY_BROKER_URL`;
- `CELERY_RESULT_BACKEND`;
- `DC_HOST`;
- `DC_WINRM_USER`;
- `DC_WINRM_PASSWORD`;
- OU и группы AD, если структура домена другая.

В Nginx меняется:

- `server_name`;
- путь `/opt/adweb/staticfiles/`, если проект лежит в другом каталоге;
- SSL-настройки, если используется HTTPS.

В systemd меняется:

- `User`;
- `Group`;
- `WorkingDirectory`;
- `EnvironmentFile`;
- путь к `.venv`, если проект лежит не в `/opt/adweb`.

