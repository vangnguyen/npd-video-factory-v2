# syntax=docker/dockerfile:1
FROM python:3.12-slim
ARG BROKER_SOURCE_HEAD
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BROKER_SOURCE_HEAD=${BROKER_SOURCE_HEAD}
LABEL org.opencontainers.image.title="npd-provider-broker" org.opencontainers.image.revision=${BROKER_SOURCE_HEAD}
WORKDIR /opt/broker
COPY pyproject.toml ./
COPY app ./app
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then PIP_CERT=/run/secrets/build_ca python -m pip install --no-cache-dir .; \
    else python -m pip install --no-cache-dir .; fi
USER 0:0
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:18084/healthz', timeout=2).close()"
CMD ["uvicorn", "npd_provider_broker.main:app", "--host", "127.0.0.1", "--port", "18084", "--no-access-log", "--log-level", "warning"]
