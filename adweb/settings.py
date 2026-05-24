import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


def env_bool(name: str, default: str = "0") -> bool:
  return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("SECRET_KEY","dev")
DEBUG = env_bool("DEBUG")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS","127.0.0.1,localhost").split(",") if h.strip()]

INSTALLED_APPS = [
  "django.contrib.admin","django.contrib.auth","django.contrib.contenttypes",
  "django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles",
  "accounts",
]
MIDDLEWARE = [
  "django.middleware.security.SecurityMiddleware",
  "django.contrib.sessions.middleware.SessionMiddleware",
  "django.middleware.common.CommonMiddleware",
  "django.middleware.csrf.CsrfViewMiddleware",
  "django.contrib.auth.middleware.AuthenticationMiddleware",
  "accounts.middleware.RequirePasswordChangeMiddleware",
  "django.contrib.messages.middleware.MessageMiddleware",
  "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "adweb.urls"
TEMPLATES = [{
  "BACKEND":"django.template.backends.django.DjangoTemplates",
  "DIRS":[BASE_DIR/"templates"],
  "APP_DIRS":True,
  "OPTIONS":{"context_processors":[
    "django.template.context_processors.debug",
    "django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth",
    "django.contrib.messages.context_processors.messages",
  ]},
}]
WSGI_APPLICATION="adweb.wsgi.application"
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
  try:
    import dj_database_url
  except ImportError as exc:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Для DATABASE_URL установите пакет dj-database-url.") from exc

  DATABASES = {
    "default": dj_database_url.parse(
      DATABASE_URL,
      conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "600")),
      ssl_require=env_bool("DB_SSL_REQUIRE"),
    )
  }
else:
  DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":BASE_DIR/"db.sqlite3"}}
AUTH_PASSWORD_VALIDATORS=[]
LANGUAGE_CODE="ru-ru"
TIME_ZONE="Europe/Moscow"
USE_I18N=True
USE_TZ=True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT")
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS")
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE")
CSRF_TRUSTED_ORIGINS = [h.strip() for h in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if h.strip()]
if env_bool("USE_X_FORWARDED_PROTO"):
  SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Аутентификация веб-интерфейса
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

LDAP_ENABLED = env_bool("LDAP_ENABLED")
LDAP_SERVER_URI = os.getenv("LDAP_SERVER_URI", "")
LDAP_BIND_DN = os.getenv("LDAP_BIND_DN", "")
LDAP_BIND_PASSWORD = os.getenv("LDAP_BIND_PASSWORD", "")
LDAP_USER_BASE_DN = os.getenv("LDAP_USER_BASE_DN", "")
LDAP_GROUP_BASE_DN = os.getenv("LDAP_GROUP_BASE_DN", "")
LDAP_REQUIRE_GROUP = os.getenv("LDAP_REQUIRE_GROUP", "").strip()
LDAP_GROUP_ADMINS_DN = os.getenv("LDAP_GROUP_ADMINS_DN", "").strip()
LDAP_GROUP_OPERATORS_DN = os.getenv("LDAP_GROUP_OPERATORS_DN", "").strip()

AUTHENTICATION_BACKENDS = [
  "django.contrib.auth.backends.ModelBackend",
]

if LDAP_ENABLED:
  import ldap
  from django_auth_ldap.config import LDAPSearch, ActiveDirectoryGroupType

  AUTHENTICATION_BACKENDS = [
    "django_auth_ldap.backend.LDAPBackend",
    "django.contrib.auth.backends.ModelBackend",
  ]

  AUTH_LDAP_SERVER_URI = LDAP_SERVER_URI
  AUTH_LDAP_BIND_DN = LDAP_BIND_DN
  AUTH_LDAP_BIND_PASSWORD = LDAP_BIND_PASSWORD
  AUTH_LDAP_USER_SEARCH = LDAPSearch(
      LDAP_USER_BASE_DN,
      ldap.SCOPE_SUBTREE,
      "(sAMAccountName=%(user)s)"
  )
  AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
      LDAP_GROUP_BASE_DN,
      ldap.SCOPE_SUBTREE,
      "(objectClass=group)"
  )
  AUTH_LDAP_GROUP_TYPE = ActiveDirectoryGroupType()
  AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
  }
  AUTH_LDAP_ALWAYS_UPDATE_USER = True
  AUTH_LDAP_FIND_GROUP_PERMS = False
  AUTH_LDAP_CACHE_TIMEOUT = 300
  AUTH_LDAP_CONNECTION_OPTIONS = {
    ldap.OPT_REFERRALS: 0,
  }
  AUTH_LDAP_MIRROR_GROUPS = False
  AUTH_LDAP_NO_NEW_USERS = True

  if LDAP_REQUIRE_GROUP:
    AUTH_LDAP_REQUIRE_GROUP = LDAP_REQUIRE_GROUP

  ldap_user_flags = {}
  if LDAP_GROUP_OPERATORS_DN:
    ldap_user_flags["is_staff"] = LDAP_GROUP_OPERATORS_DN
  if LDAP_GROUP_ADMINS_DN:
    ldap_user_flags["is_superuser"] = LDAP_GROUP_ADMINS_DN
  if ldap_user_flags:
    AUTH_LDAP_USER_FLAGS_BY_GROUP = ldap_user_flags

DC_HOST = os.getenv("DC_HOST")
DC_WINRM_PORT = int(os.getenv("DC_WINRM_PORT","5985"))
DC_WINRM_TRANSPORT = os.getenv("DC_WINRM_TRANSPORT","ntlm")
DC_WINRM_USER = os.getenv("DC_WINRM_USER")
DC_WINRM_PASSWORD = os.getenv("DC_WINRM_PASSWORD")

AD_DOMAIN_NETBIOS = os.getenv("AD_DOMAIN_NETBIOS","LAB")
AD_UPN_SUFFIX = os.getenv("AD_UPN_SUFFIX","@lab.local")
AD_HOME_PAGE = os.getenv("AD_HOME_PAGE","https://portal.muiv.ru")
AD_DEFAULT_PASSWORD = os.getenv("AD_DEFAULT_PASSWORD","Test1234!")

BRANCH_LABELS = {
  "hq": os.getenv("BRANCH_HQ_LABEL","Головной вуз"),
  "sposad": os.getenv("BRANCH_SPOSAD_LABEL","Филиал в г. Сергиев Посад"),
  "penza": os.getenv("BRANCH_PENZA_LABEL","Филиал в г. Пенза"),
  "ryazan": os.getenv("BRANCH_RYAZAN_LABEL","Филиал в г. Рязань"),
  "rostov": os.getenv("BRANCH_ROSTOV_LABEL","Филиал в г. Ростов-на-Дону"),
  "nnov": os.getenv("BRANCH_NNOV_LABEL","Филиал в г. Нижний Новгород"),
}
OU_MAP = {
  "hq": os.getenv("OU_HQ"),
  "sposad": os.getenv("OU_SPOSAD"),
  "penza": os.getenv("OU_PENZA"),
  "ryazan": os.getenv("OU_RYAZAN"),
  "rostov": os.getenv("OU_ROSTOV"),
  "nnov": os.getenv("OU_NNOV"),
}

PROFILE_HQ = os.getenv("PROFILE_HQ", r"\\serverf\pr\{login}")
HOME_HQ = os.getenv("HOME_HQ", r"\\serverhf\hf\{login}")
PROFILE_BRANCH = os.getenv("PROFILE_BRANCH", r"\\serverf\bpr\{login}")

FILESHARES_ENABLED = env_bool("FILESHARES_ENABLED")

LOGGING_ENABLED = env_bool("LOGGING_ENABLED")
LOG_FILE1 = os.getenv("LOG_FILE1","")
LOG_FILE2 = os.getenv("LOG_FILE2","")

GROUPS_HQ = [g.strip() for g in os.getenv("GROUPS_HQ","").split(",") if g.strip()]
GROUPS_HQ_F = [g.strip() for g in os.getenv("GROUPS_HQ_F","").split(",") if g.strip()]
GROUPS_BRANCH = [g.strip() for g in os.getenv("GROUPS_BRANCH","").split(",") if g.strip()]
GROUPS_BRANCH_F = [g.strip() for g in os.getenv("GROUPS_BRANCH_F","").split(",") if g.strip()]

EXCHANGE_ENABLED = env_bool("EXCHANGE_ENABLED")
EXCHANGE_URI = os.getenv("EXCHANGE_URI","")
EXCHANGE_AUTH = os.getenv("EXCHANGE_AUTH","Kerberos")
EXCHANGE_USER = os.getenv("EXCHANGE_USER","")
EXCHANGE_PASSWORD = os.getenv("EXCHANGE_PASSWORD","")
MAILBOX_DB_HQ = os.getenv("MAILBOX_DB_HQ","mailbox500")
MAILBOX_DB_BRANCH = os.getenv("MAILBOX_DB_BRANCH","mailbox50")
SMTP_SUFFIX_BRANCH = os.getenv("SMTP_SUFFIX_BRANCH","@muiv.ru")


# Мониторинг, кэш и Redis
AD_USERS_SEARCH_BASE = os.getenv("AD_USERS_SEARCH_BASE", "")
AD_ANALYTICS_MAX_DAYS = int(os.getenv("AD_ANALYTICS_MAX_DAYS", "10"))
MONITORING_CACHE_KEY = os.getenv("MONITORING_CACHE_KEY", "ad_monitoring_snapshot")
MONITORING_CACHE_TIMEOUT = int(os.getenv("MONITORING_CACHE_TIMEOUT", "120"))
MONITORING_REFRESH_SECONDS = int(os.getenv("MONITORING_REFRESH_SECONDS", "60"))
MONITORING_FRAGMENT_POLL_SECONDS = int(os.getenv("MONITORING_FRAGMENT_POLL_SECONDS", "60"))
MONITORING_FORCE_SYNC_ON_MISS = env_bool("MONITORING_FORCE_SYNC_ON_MISS")

REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
  CACHES = {
    "default": {
      "BACKEND": "django.core.cache.backends.redis.RedisCache",
      "LOCATION": REDIS_URL,
    }
  }
else:
  CACHES = {
    "default": {
      "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
      "LOCATION": "adweb-monitoring-local",
    }
  }

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL or "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_IGNORE_RESULT = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
  "refresh-ad-monitoring-snapshot": {
    "task": "accounts.tasks.refresh_ad_monitoring_snapshot",
    "schedule": MONITORING_REFRESH_SECONDS,
  }
}
