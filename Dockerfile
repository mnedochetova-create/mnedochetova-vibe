FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (better layer caching)
COPY bot/requirements.txt /app/bot/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/bot/requirements.txt \
    && python -m pip install --no-cache-dir Pillow

# Brand assets: logo → inline MP4 animations (built in image, not committed GIF)
COPY bot/assets/logo.png /app/bot/assets/logo.png
COPY bot/scripts /app/bot/scripts
RUN python3 /app/bot/scripts/generate_ui_assets.py

# Copy runtime code
COPY bot/src /app/bot/src
COPY bot/prompts /app/bot/prompts

# Runtime storage dir (file will be created by the app when needed)
RUN mkdir -p /app/bot/data

# The bot reads env vars at runtime (BOT_TOKEN, etc.)
CMD ["python", "bot/src/main.py"]
