FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY codeatlas ./codeatlas
COPY demo_repository ./demo_repository
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "codeatlas.app:app", "--host", "0.0.0.0", "--port", "8000"]

