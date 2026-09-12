FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY log_analytics ./log_analytics
RUN pip install --no-cache-dir '.[api]' \
    && useradd --system --uid 1001 analytics
USER analytics
EXPOSE 8080
CMD ["python", "-m", "log_analytics", "serve", "--host", "0.0.0.0", "--port", "8080"]
