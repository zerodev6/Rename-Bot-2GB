FROM python:3.10-slim

WORKDIR /app

# System deps in one layer — clean in same RUN to keep image small
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps before copying code
# → layer is cached and NOT rebuilt on code changes
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy app code last
COPY . .

CMD ["python3", "bot.py"]
