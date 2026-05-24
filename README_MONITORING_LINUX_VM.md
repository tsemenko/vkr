# Мониторинг AD через Redis + Celery 

## Пакеты в Debian/Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip redis-server
```

## Python-зависимости проекта

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Настройка `.env`

Минимум проверь эти переменные:

- `DC_HOST`
- `DC_WINRM_USER`
- `DC_WINRM_PASSWORD`
- `AD_USERS_SEARCH_BASE`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `MONITORING_REFRESH_SECONDS`
- `MONITORING_FRAGMENT_POLL_SECONDS`

Пример:

```env
REDIS_URL=redis://192.168.56.102:6379/1
CELERY_BROKER_URL=redis://192.168.56.102:6379/0
CELERY_RESULT_BACKEND=redis://192.168.56.102:6379/1
AD_USERS_SEARCH_BASE=OU=Users,DC=lab,DC=local
MONITORING_CACHE_TIMEOUT=120
MONITORING_REFRESH_SECONDS=15
MONITORING_FRAGMENT_POLL_SECONDS=5
MONITORING_FORCE_SYNC_ON_MISS=1
```

## Запуск вручную

### 1. Redis
```bash
sudo systemctl enable --now redis-server
redis-cli ping
```

### 2. Первый прогрев снимка мониторинга
```bash
source .venv/bin/activate
python manage.py refresh_ad_snapshot
```

### 3. Celery worker
```bash
source .venv/bin/activate
celery -A adweb worker -l info
```

### 4. Celery beat
```bash
source .venv/bin/activate
celery -A adweb beat -l info
```

### 5. Django
```bash
source .venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

## Как теперь работает мониторинг

1. Celery beat раз в `MONITORING_REFRESH_SECONDS` секунд ставит задачу на обновление.
2. Celery worker выполняет один агрегированный запрос к AD через WinRM.
3. Snapshot кладётся в Redis.
4. Django читает snapshot из кэша и быстро отдаёт страницу.
5. Браузер раз в `MONITORING_FRAGMENT_POLL_SECONDS` секунд обновляет только фрагмент мониторинга.

## systemd

Готовые примеры unit-файлов лежат в `deploy/systemd/`. Их можно использовать после подстановки имени пользователя и пути к проекту.
