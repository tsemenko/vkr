# Веб-сервис AD 

Django-проект предназначен для создания учетных записей Active Directory через веб-интерфейс.

Эта инструкция описывает  production-запуск. 
## 1. Схема работы

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
  +-- PostgreSQL — основная база данных
  +-- Redis — кэш и брокер сообщений
  +-- Celery worker — выполнение фоновых задач
  +-- Celery beat — периодический запуск мониторинга
  +-- Active Directory — создание и сопровождение учетных записей через WinRM
```

## 2. Что должно быть на сервере

Пример для Debian/Ubuntu.
```bash
apt update
apt install -y python3 python3-venv python3-pip python3-dev gcc build-essential pkg-config \
  libldap2-dev libsasl2-dev libssl-dev \
  nginx postgresql postgresql-contrib redis-server git
```

Включить основные службы:

```bash
systemctl enable --now postgresql
systemctl enable --now redis-server
systemctl enable --now nginx
```

Проверить Redis:

```bash
redis-cli ping
```

Ожидаемый ответ:

```text
PONG
```

## 3. Создание пользователя и каталога проекта

Проект будет размещаться в каталоге `/opt/adweb` и запускаться от системного пользователя `adweb`.

```bash
adduser --system --group --home /opt/adweb --shell /usr/sbin/nologin adweb
```

Скачать проект:

```bash
rm -rf /opt/adweb
git clone https://github.com/tsemenko/vkr.git /opt/adweb
chown -R adweb:www-data /opt/adweb
```

Перейти в каталог проекта:

```bash
cd /opt/adweb
```

# Настройка базы данных PostgreSQL


На сервере с Django-приложением не требуется устанавливать и настраивать PostgreSQL, если база данных уже развернута на отдельном сервере. На сервере приложения устанавливаются только Python-зависимости для подключения к PostgreSQL.

Django подключается к PostgreSQL через переменную окружения `DATABASE_URL`, которая указывается в файле `.env`.

## Подключение к внешнему PostgreSQL

Пример строки подключения:

```env
DATABASE_URL=postgres://adweb_user:strong_password@192.168.1.20:5432/adweb_db
```

Где:

```text
adweb_user       — пользователь PostgreSQL
strong_password  — пароль пользователя PostgreSQL
192.168.1.20     — IP-адрес сервера PostgreSQL
5432             — порт PostgreSQL
adweb_db         — имя базы данных
```

На сервере PostgreSQL заранее должны быть созданы база данных и пользователь с правами на эту базу.

После настройки `.env` на сервере приложения необходимо выполнить миграции Django:

```bash
cd /opt/adweb
source .venv/bin/activate
python manage.py migrate
```

## Создание базы данных PostgreSQL

Если PostgreSQL разворачивается на этом же сервере.

```bash
runuser -u postgres -- psql
```

Внутри `psql` выполнить:

```sql
CREATE USER adweb_user WITH PASSWORD 'change-me-strong-password';
CREATE DATABASE adweb_db OWNER adweb_user;
ALTER ROLE adweb_user SET client_encoding TO 'utf8';
ALTER ROLE adweb_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE adweb_user SET timezone TO 'Europe/Moscow';
\q
```

Для PostgreSQL 15 и выше дополнительно выполнить:

```bash
runuser -u postgres -- psql -d adweb_db -c "GRANT ALL ON SCHEMA public TO adweb_user;"
```

## Проверка подключения

После указания `DATABASE_URL` можно проверить подключение через Django:

```bash
cd /opt/adweb
source .venv/bin/activate
python manage.py check
python manage.py migrate
```

Если команды выполняются без ошибок, приложение успешно подключается к PostgreSQL.


## 5. Python-окружение и зависимости

Создать виртуальное окружение и установить зависимости:

```bash
cd /opt/adweb
runuser -u adweb -- python3 -m venv .venv
runuser -u adweb -- /opt/adweb/.venv/bin/python -m pip install --upgrade pip
runuser -u adweb -- /opt/adweb/.venv/bin/python -m pip install -r requirements-prod.txt
```

## 6. Production `.env`

Создать файл окружения:

```bash
cd /opt/adweb
cp .env.example .env
nano .env
```

Минимальный пример production-настроек:

```env
# Django
SECRET_KEY=change-me-long-random-secret-key
DEBUG=0
ALLOWED_HOSTS=adweb.example.local,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://adweb.example.local,http://adweb.example.local

# PostgreSQL
DATABASE_URL=postgres://adweb_user:change-me-strong-password@127.0.0.1:5432/adweb
DB_CONN_MAX_AGE=600
DB_SSL_REQUIRE=0

# HTTPS через Nginx
SECURE_SSL_REDIRECT=0
SESSION_COOKIE_SECURE=0
CSRF_COOKIE_SECURE=0
USE_X_FORWARDED_PROTO=1
SECURE_HSTS_SECONDS=0
SECURE_HSTS_INCLUDE_SUBDOMAINS=0
SECURE_HSTS_PRELOAD=0

# WinRM / Active Directory
DC_HOST=192.168.56.10
DC_WINRM_PORT=5985
DC_WINRM_TRANSPORT=ntlm
DC_WINRM_USER=LAB\svc.account.creator
DC_WINRM_PASSWORD=change-me

# Домен и правила именования
AD_DOMAIN_NETBIOS=LAB
AD_UPN_SUFFIX=@lab.local
AD_HOME_PAGE=https://portal.muiv.ru
AD_DEFAULT_PASSWORD=change-me

# LDAP-вход в веб-интерфейс
LDAP_ENABLED=0
LDAP_SERVER_URI=ldap://dc01.lab.local:389
LDAP_BIND_DN=CN=svc_ldap,OU=Admin,OU=Managed,OU=Domain Users,DC=lab,DC=local
LDAP_BIND_PASSWORD=change-me
LDAP_USER_BASE_DN=DC=lab,DC=local
LDAP_GROUP_BASE_DN=DC=lab,DC=local
LDAP_REQUIRE_GROUP=
LDAP_GROUP_ADMINS_DN=
LDAP_GROUP_OPERATORS_DN=

# OU для создания учетных записей
OU_HQ=OU=all,OU=Managed,OU=Domain Users,DC=lab,DC=local


# Группы AD по умолчанию
GROUPS_HQ=
GROUPS_BRANCH=

# Профили и домашние папки
PROFILE_HQ=\\serverf\pr\{login}
HOME_HQ=\\serverhf\hf\{login}
PROFILE_BRANCH=\\serverf\bpr\{login}
FILESHARES_ENABLED=0

# Exchange, если не используется — оставить 0
EXCHANGE_ENABLED=0
EXCHANGE_URI=http://serverexcha/PowerShell/
EXCHANGE_AUTH=Kerberos
EXCHANGE_USER=MIEMP\exchange_admin
EXCHANGE_PASSWORD=change-me
MAILBOX_DB_HQ=mailbox500
MAILBOX_DB_BRANCH=mailbox50
SMTP_SUFFIX_BRANCH=@muiv.ru

# Redis / Celery / мониторинг
AD_USERS_SEARCH_BASE=OU=all,OU=Managed,OU=Domain Users,DC=lab,DC=local
AD_ANALYTICS_MAX_DAYS=10
REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
MONITORING_CACHE_KEY=ad_monitoring_snapshot
MONITORING_CACHE_TIMEOUT=120
MONITORING_REFRESH_SECONDS=60
MONITORING_FRAGMENT_POLL_SECONDS=60
MONITORING_FORCE_SYNC_ON_MISS=1
```

Ограничить права на `.env`:

```bash
chown adweb:www-data /opt/adweb/.env
chmod 640 /opt/adweb/.env
```

Важно: `.env` содержит пароли и не должен храниться в Git.

## 7. Проверка Django, миграции и статика

```bash
cd /opt/adweb
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py check
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py migrate
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py collectstatic --noinput
```

Создать базовые роли веб-интерфейса:

```bash
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py bootstrap_web_roles
```

Загрузить базовую конфигурацию филиалов, OU и правил, если команда используется в проекте:

```bash
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py bootstrap_directory_config
```

Создать администратора Django:

```bash
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py createsuperuser
```

Или создать пользователя веб-интерфейса через команду проекта:

```bash
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py provision_web_user admin --groups "AD Super Admins" --superuser
```

## 8. Gunicorn через systemd

В проекте должен быть файл:

```text
deploy/systemd/gunicorn.service.example
```

Скопировать его в systemd:

```bash
cp /opt/adweb/deploy/systemd/gunicorn.service.example /etc/systemd/system/adweb-gunicorn.service
nano /etc/systemd/system/adweb-gunicorn.service
```

Нормальный вариант службы:

```ini
[Unit]
Description=Gunicorn for adweb
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=adweb
Group=www-data
WorkingDirectory=/opt/adweb
EnvironmentFile=/opt/adweb/.env
Environment=DJANGO_SETTINGS_MODULE=adweb.settings
RuntimeDirectory=adweb
ExecStart=/opt/adweb/.venv/bin/gunicorn adweb.wsgi:application --bind unix:/run/adweb/gunicorn.sock --workers 3 --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

Запустить службу:

```bash
systemctl daemon-reload
systemctl enable --now adweb-gunicorn
systemctl status adweb-gunicorn --no-pager
```

Проверить сокет:

```bash
ls -la /run/adweb/gunicorn.sock
```

## 9. Nginx

В проекте должен быть файл:

```text
deploy/nginx/adweb.conf.example
```

Скопировать конфиг:

```bash
cp /opt/adweb/deploy/nginx/adweb.conf.example /etc/nginx/sites-available/adweb
nano /etc/nginx/sites-available/adweb
```

Нормальный вариант Nginx-конфига без HTTPS:

```nginx
server {
    listen 80;
    server_name adweb.example.local;

    client_max_body_size 20m;

    location /static/ {
        alias /opt/adweb/staticfiles/;
    }

    location / {
        proxy_pass http://unix:/run/adweb/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Включить сайт:

```bash
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/adweb /etc/nginx/sites-enabled/adweb
nginx -t
systemctl reload nginx
```

Проверить ответ сайта:

```bash
curl -I http://127.0.0.1/
```

## 10. HTTPS

Если есть домен и нужен HTTPS, установить Certbot:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d adweb.example.local
```

После успешной настройки HTTPS поменять в `.env`:

```env
CSRF_TRUSTED_ORIGINS=https://adweb.example.local
SECURE_SSL_REDIRECT=1
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
USE_X_FORWARDED_PROTO=1
```

Перезапустить службы:

```bash
systemctl restart adweb-gunicorn
systemctl reload nginx
```

HSTS включать только после проверки HTTPS:

```env
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=1
SECURE_HSTS_PRELOAD=1
```

## 11. Celery worker и Celery beat

Скопировать службы:

```bash
cp /opt/adweb/deploy/systemd/celery-worker.service.example /etc/systemd/system/adweb-celery-worker.service
cp /opt/adweb/deploy/systemd/celery-beat.service.example /etc/systemd/system/adweb-celery-beat.service
```

Проверить содержимое файлов:

```bash
nano /etc/systemd/system/adweb-celery-worker.service
nano /etc/systemd/system/adweb-celery-beat.service
```

Нормальная служба Celery worker:

```ini
[Unit]
Description=Celery Worker for adweb
After=network.target redis-server.service

[Service]
Type=simple
User=adweb
Group=adweb
WorkingDirectory=/opt/adweb
EnvironmentFile=/opt/adweb/.env
Environment=DJANGO_SETTINGS_MODULE=adweb.settings
ExecStart=/opt/adweb/.venv/bin/celery -A adweb worker -l info
Restart=always

[Install]
WantedBy=multi-user.target
```

Нормальная служба Celery beat:

```ini
[Unit]
Description=Celery Beat for adweb
After=network.target redis-server.service

[Service]
Type=simple
User=adweb
Group=adweb
WorkingDirectory=/opt/adweb
EnvironmentFile=/opt/adweb/.env
Environment=DJANGO_SETTINGS_MODULE=adweb.settings
ExecStart=/opt/adweb/.venv/bin/celery -A adweb beat -l info
Restart=always

[Install]
WantedBy=multi-user.target
```

Запустить Celery:

```bash
systemctl daemon-reload
systemctl enable --now adweb-celery-worker adweb-celery-beat
systemctl status adweb-celery-worker --no-pager
systemctl status adweb-celery-beat --no-pager
```

Проверить Celery:

```bash
cd /opt/adweb
runuser -u adweb -- /opt/adweb/.venv/bin/celery -A adweb inspect ping
```

Ожидаемый результат:

```text
pong
```

## 12. Проверка связи с Active Directory

Проверить доступность WinRM-порта контроллера домена:

```bash
nc -vz 192.168.56.10 5985
```

Если команды `nc` нет:

```bash
apt install -y netcat-openbsd
nc -vz 192.168.56.10 5985
```

Проверить ручное обновление снимка мониторинга AD:

```bash
cd /opt/adweb
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py refresh_ad_snapshot
```

Если команда завершается ошибкой, проверить в `.env`:

```text
DC_HOST
DC_WINRM_PORT
DC_WINRM_TRANSPORT
DC_WINRM_USER
DC_WINRM_PASSWORD
AD_USERS_SEARCH_BASE
OU_HQ / OU филиалов
```

## 13. Проверка production-состояния

```bash
cd /opt/adweb
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py check --deploy
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py test
systemctl status adweb-gunicorn --no-pager
systemctl status adweb-celery-worker --no-pager
systemctl status adweb-celery-beat --no-pager
nginx -t
redis-cli ping
curl -I http://127.0.0.1/
```

## 14. Обновление проекта на сервере

```bash
cd /opt/adweb
git pull
chown -R adweb:www-data /opt/adweb
runuser -u adweb -- /opt/adweb/.venv/bin/python -m pip install -r requirements-prod.txt
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py migrate
runuser -u adweb -- /opt/adweb/.venv/bin/python manage.py collectstatic --noinput
systemctl restart adweb-gunicorn adweb-celery-worker adweb-celery-beat
nginx -t
systemctl reload nginx
```

## 15. Резервное копирование

Создать каталог для резервных копий:

```bash
mkdir -p /opt/backups/adweb
```

Сделать дамп PostgreSQL:

```bash
pg_dump -U adweb_user -h 127.0.0.1 adweb > /opt/backups/adweb/adweb_$(date +%F_%H-%M).sql
```

Сохранить `.env` отдельно:

```bash
cp /opt/adweb/.env /opt/backups/adweb/env_$(date +%F_%H-%M).backup
chmod 600 /opt/backups/adweb/env_*.backup
```

