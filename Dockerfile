FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install chromium && \
    python -m playwright install-deps chromium || true

COPY . .

VOLUME ["/app/JioData"]

CMD ["python", "-u", "bot.py"]
