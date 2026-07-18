FROM python:3.14-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir streamlink playwright requests pycryptodome pycountry

RUN playwright install chromium

WORKDIR /app
COPY main.py .

ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

ENTRYPOINT ["python", "main.py"]
