FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        g++ \
        unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.prod.txt /app/requirements.prod.txt

RUN pip install --no-cache-dir -r /app/requirements.prod.txt

RUN addgroup --system django \
    && adduser --system --ingroup django django

COPY --chown=django:django . /app

RUN mkdir -p /app/media /app/staticfiles \
    && chown -R django:django /app/media /app/staticfiles \
    && chmod +x /app/entrypoint.sh

USER django

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), 2).close()" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
