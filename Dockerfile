FROM python:3.11-slim

ENV BOT_UI_VERSION=2026-05-28-thinking-logo
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY bot/requirements.txt /app/bot/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/bot/requirements.txt \
    && python -m pip install --no-cache-dir Pillow

COPY bot/assets/logo.png /app/bot/assets/logo.png
COPY bot/scripts /app/bot/scripts
RUN python3 /app/bot/scripts/generate_ui_assets.py

COPY bot/src /app/bot/src
COPY bot/prompts /app/bot/prompts

RUN mkdir -p /app/bot/data

CMD ["python", "bot/src/main.py"]
