FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching)
COPY bot/requirements.txt /app/bot/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/bot/requirements.txt

# Copy only the bot runtime code/assets
COPY bot/src /app/bot/src
COPY bot/prompts /app/bot/prompts
COPY bot/data /app/bot/data

# The bot reads env vars at runtime (BOT_TOKEN, etc.)
CMD ["python", "bot/src/main.py"]

