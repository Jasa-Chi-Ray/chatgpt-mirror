import os
from pathlib import Path


def env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", True)
SHOW_GITHUB = env_bool("SHOW_GITHUB", True)
FREE_ACCOUNT_USERNAME = os.environ.get("FREE_ACCOUNT_USERNAME", "free_account")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
GATEWAY_ADMIN_SECRET = os.environ.get("GATEWAY_ADMIN_SECRET", "")
ALLOW_REGISTER = env_bool("ALLOW_REGISTER", True)
CHATGPT_GATEWAY_URL = os.environ.get("CHATGPT_GATEWAY_URL", "http://chatgpt-mirror:40002")

BASE_DIR = Path(__file__).resolve().parent.parent
log_file_path = os.path.join(BASE_DIR, os.pardir, 'logs/cron.log')

CRONJOBS = [
    ('*/1 * * * *', 'app.cron.check_access_token', f'>> {log_file_path}'),
    ('*/1 * * * *', 'app.cron.update_access_token', f'>> {log_file_path}'),

]
