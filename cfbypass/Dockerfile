FROM python:3.12-slim

ENV LANG=C.UTF-8 \
    TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    xauth \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY cfbypass/requirements.txt ./requirements.txt
RUN pip install -U pip && pip install -r requirements.txt

COPY cfbypass/app.py ./app.py

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
