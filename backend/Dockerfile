# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached and only
# rebuilds when requirements.txt actually changes, not on every
# source code edit.
COPY requirements.txt .
COPY pyproject.toml .
RUN pip install -r requirements.txt

# Now copy the application source.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts
COPY evaluation ./evaluation
COPY tests ./tests

EXPOSE 8000

# Apply any pending migrations, then start the API server. `alembic
# upgrade head` is a no-op when there are no migrations yet (M0) and
# becomes meaningful from M1 onward once models/revisions exist.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
