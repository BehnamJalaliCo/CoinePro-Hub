# syntax=docker/dockerfile:1.7
# substitute-runner (prompt 12 §9.1, contract §21.13): the substitute players'
# official CLIs, one process per call, never a service. OpenAI Codex CLI
# (Apache-2.0) and Google Gemini CLI (Apache-2.0) at the versions of
# substitutes/cli/package-lock.json (npm ci: every package checked against its
# integrity hash; no install scripts run), driven by the stdlib wrapper
# hq_substitutes: the Job JSON on stdin, the prompt to the CLI on ITS stdin
# (never in argv), JSON lines on stdout. uid 10001 on a read-only root; compose
# adds the tmpfs working directory and the sign-in volume (/auth).
FROM node:22.22.0-trixie-slim AS cli
WORKDIR /opt/cli
COPY substitutes/cli/package.json substitutes/cli/package-lock.json ./
# The voice host (speech, never used here) is left out of the image.
RUN npm ci --ignore-scripts --omit=dev --no-audit --no-fund \
    && npm cache clean --force \
    && rm -rf /root/.npm \
        node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/codex-resources/voice

FROM python:3.12.15-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/hq-common/src:/app/substitutes/src \
    PATH=/opt/cli/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/work/.home \
    NO_UPDATE_NOTIFIER=1
COPY --from=cli /usr/local/bin/node /usr/local/bin/node
COPY --from=cli /opt/cli /opt/cli
# Gemini's system settings (above every user setting): no core tool at all, or
# the read-only file tools of a code review (review.json); no MCP, extension,
# telemetry or update. Root-owned: Gemini refuses a writable settings dir.
COPY substitutes/etc/gemini-cli/ /etc/gemini-cli/
COPY substitutes/schemas /app/substitutes/schemas
COPY hq-common/src /app/hq-common/src
COPY substitutes/src /app/substitutes/src
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq \
    && node --version \
    && HOME=/tmp codex --version \
    && HOME=/tmp gemini --version \
    && rm -rf /tmp/.codex /tmp/.gemini
USER 10001
WORKDIR /work
ENTRYPOINT ["python", "-m", "hq_substitutes"]
