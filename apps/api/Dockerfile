FROM python:3.12-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ocrmypdf tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng tesseract-ocr-ron \
        poppler-utils img2pdf postgresql-client rsync \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8765
CMD ["uvicorn", "mona.app:app", "--host", "0.0.0.0", "--port", "8765"]
