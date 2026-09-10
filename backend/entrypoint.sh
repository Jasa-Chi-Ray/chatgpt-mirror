#!/bin/sh
set -e

mkdir -p /app/backend/logs /app/backend/db

python manage.py migrate --noinput
python cli/create_init_user.py

python manage.py retry_gateway_revocations &
retry_pid=$!
python manage.py runserver 0.0.0.0:8000 --noreload &
server_pid=$!
shutdown() {
    result=$?
    trap - INT TERM EXIT
    kill "$retry_pid" "$server_pid" 2>/dev/null || true
    wait || true
    exit "$result"
}
trap shutdown EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
while kill -0 "$retry_pid" 2>/dev/null && kill -0 "$server_pid" 2>/dev/null; do
    sleep 1
done
exit 1
