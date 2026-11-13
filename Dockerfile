FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . uvicorn
COPY config ./config
COPY models ./models
COPY examples ./examples
ENV PYTHONUNBUFFERED=1 \
    MODEL_PATH=/app/models/verifier.json \
    VAULT_PATH=/app/examples/vault.json
USER app
EXPOSE 8080
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "accuracy.service.main:app", "--host", "0.0.0.0", "--port", "8080"]
