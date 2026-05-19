#!/bin/sh
set -e

mkdir -p /app/backend/logs /app/backend/db

python manage.py migrate --noinput
python cli/create_init_user.py

exec python manage.py runserver 0.0.0.0:8000
