FROM mcr.microsoft.com/playwright/python:v1.65.1-noble

RUN groupadd --system grocery && useradd --system --gid grocery --create-home grocery

WORKDIR /app

COPY pyproject.toml README.md ./
COPY grocery_mcp ./grocery_mcp

RUN pip install --no-cache-dir . \
    && chmod -R a+rX /ms-playwright

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

USER grocery

EXPOSE 8080

CMD ["sh", "-c", "python -m grocery_mcp.server --http --host 0.0.0.0 --port ${PORT:-8080}"]
