FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade --retries 5 --timeout 120 \
    --index-url https://pypi.org/simple \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    --trusted-host pypi.python.org \
    pip setuptools wheel \
 && python -m pip install --no-cache-dir --retries 5 --timeout 120 \
    --index-url https://pypi.org/simple \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    --trusted-host pypi.python.org \
    -r /app/requirements.txt

# Before COPY so code-only rebuilds reuse this layer; --with-deps needs apt.
RUN python -m playwright install --with-deps chromium

COPY . /app

EXPOSE 8000
