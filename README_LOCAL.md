
````markdown
# Локальный запуск проекта adweb

Эта инструкция описывает запуск Django-проекта `adweb` из локальной папки проекта на Windows и Linux.

## Схемы запуска

### Вариант 1. Django запускается на Windows

```text
Windows
  Django runserver
  SQLite db.sqlite3
  .venv

Linux ВМ IP
  Redis
  Celery worker
  Celery beat

AD ВМ IP
  Active Directory
  WinRM 5985
````

### Django запускается на Linux

```text
Linux ВМ IP
  Django runserver
  SQLite db.sqlite3
  .venv
  Redis
  Celery worker
  Celery beat

AD ВМ IP
  Active Directory
  WinRM 5985
```
## Подготовка окружения на Windows

Из папки проекта:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
```

Если виртуальное окружение уже есть, достаточно проверить Python:

```powershell
.\.venv\Scripts\python.exe --version
```

## Подготовка окружения на Linux

Перейди в папку проекта:

```bash
cd 
```

Установи системные пакеты:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip redis-server build-essential python3.11-dev libldap2-dev libsasl2-dev libssl-dev
```

Создай виртуальное окружение:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Если виртуальное окружение уже есть, проверь Python:

```bash
source .venv/bin/activate
python --version
```

## Настройка `.env`

Создай `.env` из примера.

На Windows:

```powershell
Copy-Item .env.example .env
```

На Linux:

```bash
cp .env.example .env
```

Для локальной схемы проверь значения:

```env
DEBUG=1
ALLOWED_HOSTS=

DC_HOST=
DC_WINRM_PORT=5985
DC_WINRM_TRANSPORT=ntlm

LDAP_ENABLED=0

REDIS_URL=
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
```

Если Django, Redis и Celery запускаются на одной Linux-машине, можно использовать локальный Redis:

```env
REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

Пароли, ключи и реальные учетные данные хранятся только в `.env`.

## Миграции и первичная настройка

### Windows

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py bootstrap_web_roles
.\.venv\Scripts\python.exe manage.py bootstrap_directory_config
```

Создание администратора веб-интерфейса:

```powershell
.\.venv\Scripts\python.exe manage.py provision_web_user admts --groups "AD Super Admins" --superuser
```

### Linux

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py bootstrap_web_roles
python manage.py bootstrap_directory_config
```

Создание администратора веб-интерфейса:

```bash
python manage.py provision_web_user admts --groups "AD Super Admins" --staff
```

Команда выдаст временный пароль. При первом входе пользователь должен поменять пароль.

## Проверка перед запуском

### Windows

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
```

Проверка Redis с Windows:

```powershell
.\.venv\Scripts\python.exe -c "import redis; r=redis.Redis(host='...', port=..., db=0); print(r.ping())"
```

Ожидаемый результат:

```text
True
```

### Linux

```bash
source .venv/bin/activate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Проверка Redis на Linux:

```bash
redis-cli ping
```

Ожидаемый результат:

```text
PONG
```

Проверка Redis через Python:

```bash
python -c "import redis; r=redis.Redis(host='127.0.0.1', port=6379, db=0); print(r.ping())"
```

Ожидаемый результат:

```text
True
```

## Запуск Redis на Linux

Если Redis установлен на Linux-машине:

```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server
sudo systemctl status redis-server --no-pager
```

Проверка:

```bash
redis-cli ping
```

Ожидаемый результат:

```text
PONG
```

## Запуск Celery на Linux

Celery нужен для обновления мониторинга Active Directory.
Если мониторинг не проверяется, Django можно запустить без Celery, но данные мониторинга не будут обновляться автоматически.

Запуск Celery worker:

```bash
source .venv/bin/activate
celery -A adweb worker -l info
```

Во втором терминале запуск Celery beat:

```bash
source .venv/bin/activate
celery -A adweb beat -l info
```

Если для проекта уже настроены systemd-службы, можно запускать их так:

```bash
sudo systemctl start celery-worker.service
sudo systemctl start celery-beat.service

sudo systemctl status celery-worker.service --no-pager
sudo systemctl status celery-beat.service --no-pager
```

## Запуск Django на Windows

```powershell
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

Открыть в браузере:

```text
http://0.0.0.0:8000/
```

## Запуск Django на Linux

Если нужно открыть проект только с самой Linux-машины:

```bash
source .venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

Открыть:

```text
http://0.0.0.0:8000/
```

В`.env` в `ALLOWED_HOSTS` должен быть указан IP Linux-машины:

```env
ALLOWED_HOSTS=127.0.0.1,localhost,0.0.0.0,
```

## Проверка подключения к AD

Django взаимодействует с контроллером домена через WinRM.

Проверка доступности порта WinRM с Windows:

```powershell
Test-NetConnection IP -Port 5985
```

Проверка доступности порта WinRM с Linux:

```bash
nc -vz 192.168.56.10 5985
```

Ожидаемый результат — порт `5985` должен быть доступен.

## Как работает проект

Проект предоставляет веб-интерфейс для работы с учетными записями Active Directory:

* создает пользователей AD через WinRM и PowerShell;
* назначает OU, UPN, временный пароль, группы, профиль и домашнюю папку;
* создает почтовый ящик Exchange;
* показывает мониторинг AD по филиалам;
* разблокирует пользователей;
* ведет журналы операций и ошибок;
* управляет филиалами, AD-группами, правилами, ролями и пользователями веб-интерфейса.

Мониторинг обновляется через Celery. Django читает готовый снимок из Redis, поэтому для полноценной проверки мониторинга должны работать Redis, Celery worker и Celery beat.

```
```
