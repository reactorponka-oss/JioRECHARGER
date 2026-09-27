FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Force chromium + all system deps
RUN python -m playwright install chromium && \
    python -m playwright install-deps chromium || true

# Verify chromium is installed
RUN ls -la /ms-playwright/ && \
    find /ms-playwright -name "chrome" -o -name "headless_shell" | head -5

COPY . .

VOLUME ["/app/JioData"]

CMD ["python", "-u", "bot.py"]
