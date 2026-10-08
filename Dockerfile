FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv==0.11.23
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable \
    && useradd --uid 10001 --create-home copilot \
    && mkdir /app/data && chown copilot:copilot /app/data
USER copilot
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "mostrador.backoffice_api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
