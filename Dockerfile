FROM python:3.12-slim

RUN groupadd --system grocery && useradd --system --gid grocery grocery

WORKDIR /app

COPY pyproject.toml README.md ./
COPY grocery_mcp ./grocery_mcp

RUN pip install --no-cache-dir .

USER grocery

EXPOSE 8080

CMD ["sh", "-c", "python -m grocery_mcp.server --http --host 0.0.0.0 --port ${PORT:-8080}"]
