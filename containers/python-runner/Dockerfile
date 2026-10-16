FROM python:3.13-slim-bookworm

ARG PYTEST_VERSION=8.4.2

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN python -m pip install --no-cache-dir "pytest==${PYTEST_VERSION}"

COPY containers/python-runner/entrypoint.py /opt/counterguard/entrypoint.py

USER 65532:65532
ENTRYPOINT ["python", "-I", "/opt/counterguard/entrypoint.py"]
