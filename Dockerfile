FROM python:3.10-slim

# ── Labels ────────────────────────────────────────────────────────────────────
LABEL maintainer="Jishu Developer @JishuDeveloper" \
      channel="@MadflixBotz" \
      version="1.0"

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
# ffmpeg        : video encoding / probing
# ffprobe       : stream analysis (bundled with ffmpeg)
# wget + ca-certs: secure downloads if needed at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        wget \
        ca-certificates \
        tzdata \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ── Timezone (optional — set to your preferred zone) ──────────────────────────
ENV TZ=Asia/Colombo

# ── Python env flags ──────────────────────────────────────────────────────────
# PYTHONDONTWRITEBYTECODE : no .pyc clutter in the image
# PYTHONUNBUFFERED        : logs print instantly (important for Telegram bots)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── Temp / download directory for the bot ─────────────────────────────────────
RUN mkdir -p /app/downloads /app/uploads /app/thumb

# ── Python dependencies ───────────────────────────────────────────────────────
# Copied BEFORE app code so Docker cache skips this layer on code-only changes
COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Non-root user (security best practice) ────────────────────────────────────
RUN useradd -m -u 1000 botuser \
    && chown -R botuser:botuser /app
USER botuser

# ── Healthcheck — confirms bot process is alive ───────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD pgrep -f "python3 bot.py" || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["python3", "bot.py"]
