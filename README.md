# Веб-сервис AD

Django-проект для работы с учетными записями Active Directory через веб-интерфейс.

## Возможности

- Создание пользователей Active Directory.
- Мониторинг AD по филиалам: истекающие пароли, неактивные и заблокированные пользователи.
- Разблокировка пользователей из интерфейса.
- Управление филиалами, AD-группами, правилами, ролями и пользователями веб-интерфейса.
- Журналы успешных операций, ошибок и системных изменений.

## Документация по запуску

- [README_LOCAL.md](README_LOCAL.md) — локальный запуск на Windows.
- [README_PRODUCTION.md](README_PRODUCTION.md) — production-запуск на Linux с Nginx, Gunicorn, PostgreSQL, Redis и Celery.
- [README_MONITORING_LINUX_VM.md](README_MONITORING_LINUX_VM.md) — отдельная схема мониторинга на Linux ВМ.

## Основные каталоги

- `adweb/` — настройки Django, URL, Celery-приложение.
- `accounts/` — основная логика проекта.
- `templates/` — HTML-шаблоны.
- `deploy/systemd/` — примеры systemd-служб.
- `deploy/nginx/` — пример Nginx-конфига.

## Что не хранится в Git


Для настройки окружения используется `.env.example` или `.env.production.example`.
