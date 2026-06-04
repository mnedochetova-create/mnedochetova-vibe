FROM python:3.11-slim

ENV BOT_UI_VERSION=2026-05-28-corner-defer-visibility

WORKDIR /app

COPY bot/requirements.txt /app/bot/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/bot/requirements.txt

COPY bot/src /app/bot/src
COPY bot/prompts /app/bot/prompts
COPY bot/assets /app/bot/assets

RUN mkdir -p /app/bot/data

CMD ["python", "bot/src/main.py"]
