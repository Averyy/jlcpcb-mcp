FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck and build deps for curl_cffi
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install dependencies
RUN pip install --no-cache-dir .

# Environment
ENV PYTHONUNBUFFERED=1
ENV HTTP_PORT=8080
ENV RATE_LIMIT_REQUESTS=100

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "-m", "jlcpcb_mcp.server"]
