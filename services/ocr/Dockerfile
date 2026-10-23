# ocr: Persian and English text from scans on the hub's CPU (prompt 14 §4,
# contract §23.9): Tesseract 5 (Apache-2.0) with the pinned fas + eng
# traineddata read from the ocr-models volume (TESSDATA_PREFIX; the packaged
# data is removed so nothing else can be read), poppler-utils' pdftoppm
# (GPL-2.0) for a scanned PDF's pages. No pip package: the service and its
# fetch job are the standard library. The same image runs the one-shot
# fetch (python -m hq_ocr.fetch). Runs as uid 10001 on a read-only root
# filesystem (compose adds the tmpfs) with no network but hq-ocr.
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/hq-common/src:/app/ocr/src \
    HOME=/tmp/home \
    OMP_THREAD_LIMIT=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr=5.5.0-1+b1 poppler-utils=25.03.0-5+deb13u4 \
    && rm -rf /var/lib/apt/lists/* /usr/share/tesseract-ocr/5/tessdata/*.traineddata \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq \
    && mkdir -p /models && chown 10001:10001 /models

COPY hq-common/src /app/hq-common/src
COPY --chmod=0644 ocr/model.lock.json /app/ocr/model.lock.json
COPY ocr/src /app/ocr/src

USER 10001
WORKDIR /app/ocr
EXPOSE 8088
CMD ["python", "-m", "hq_ocr"]
