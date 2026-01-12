FROM python:3.14.1-slim

WORKDIR /

RUN apt-get update && \
    apt-get install -y --no-install-recommends git gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir uv

ENV PYTHONPATH=${PYTHONPATH}:/app

COPY pyproject.toml /pyproject.toml
COPY README.md /README.md

RUN uv pip install --system --no-cache-dir -e .
RUN mkdir -p static/uploads

COPY app/boot.sh /boot.sh
COPY app/main.py /main.py
COPY app/migrations/ /migrations/
COPY app/alembic.ini /alembic.ini

COPY app/app/ /app/

RUN useradd -r -s /bin/false -m celery && \
    mkdir -p /home/celery/ && \
    chown -R celery:celery /home/celery

