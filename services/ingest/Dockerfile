FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
RUN useradd --create-home --uid 10001 ingest

COPY src ./src
RUN pip install --no-cache-dir --no-deps .

USER ingest

ENTRYPOINT ["python", "-m", "ingest"]

FROM base AS runtime

FROM base AS test
USER root
COPY requirements-dev.lock ./
RUN pip install --no-cache-dir -r requirements-dev.lock
COPY tests ./tests
USER ingest
ENTRYPOINT ["pytest"]
CMD ["-q", "tests"]
