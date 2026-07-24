# syntax=docker/dockerfile:1.7
ARG PDP_DOCKER_REGISTRY=docker.arvancloud.ir/library
FROM ${PDP_DOCKER_REGISTRY}/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app
COPY requirements.txt .

# Keep successfully downloaded wheels between builds and tolerate temporary
# DNS/Internet interruptions on the Windows trial host.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefer-binary --retries 10 --timeout 120 -r requirements.txt

COPY . .
RUN mkdir -p /data/private
EXPOSE 8000
