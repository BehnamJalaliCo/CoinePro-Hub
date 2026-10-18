# provisioner (prompt 09 §4): builds a server the owner sealed, through the
# Hetzner Cloud API only (egress's provisioner proxy). Code, not an agent.
# uid 10001, read-only root filesystem (compose adds the tmpfs). The cloud-init
# templates are mounted read-only from infra/provisioning/templates.
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/hq-common/src:/app/provisioner/src

COPY provisioner/requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq

COPY hq-common/src /app/hq-common/src
COPY provisioner/src /app/provisioner/src

USER 10001
WORKDIR /app/provisioner
EXPOSE 8110
CMD ["python", "-m", "hq_provisioner"]
