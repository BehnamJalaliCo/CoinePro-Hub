# media-render: the media studio's sandboxed render worker (prompt 13 §2.3,
# contract §22.2 step 6). One image, two one-shots of the opt-in profile
# "media" (infra/media/run-once.sh, under the one-shot lock):
#   courier  on hq-media (the api and OpenBao only): claims a job into the job
#            volume, later sends the outputs back;
#   render   with no network at all: headless Chromium (Playwright, its own
#            sandbox on: Playwright's seccomp profile, SYS_CHROOT only) draws
#            the composition frame by frame; ffmpeg muxes voice and captions.
# The official Playwright image is pinned by digest (its Chromium matches
# playwright==1.63.0, like the egress browser); ffmpeg pinned to the exact
# Ubuntu noble version; anime.js and lottie-web (light) from their npm
# tarballs, checked by sha256 (assets.lock.json); IRANYekanX from
# design/fonts/static (named build context "design"), installed as the only
# font a composition may name. uid 10001; writes only /tmp and /jobs.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/tmp \
    PYTHONPATH=/app/hq-common/src:/app/media-render/src \
    MEDIA_LIB_DIR=/opt/hq-media/lib \
    MEDIA_FONT_DIR=/opt/hq-media/fonts \
    MEDIA_JOBS_DIR=/jobs

# ffmpeg/ffprobe (Ubuntu noble, exact version): H.264 (libx264), AAC, Opus in.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg=7:6.1.1-3ubuntu5 \
    && rm -rf /var/lib/apt/lists/*

COPY media-render/requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --require-hashes --no-deps --break-system-packages -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq \
    && install -d -o 10001 -g 10001 -m 0700 /jobs

# The only scripts a composition may load (/lib/anime.min.js, /lib/lottie.min.js).
ADD --checksum=sha256:a1a952d2265ff27a500945443a0752157d021c193b47ca2e5bf4ada61a6ff8b6 \
    https://registry.npmjs.org/animejs/-/animejs-3.2.2.tgz /tmp/animejs.tgz
ADD --checksum=sha256:8600b50a5cecc3d327f32e62f744812f4dbe9279469280117d7e64f59fb343c2 \
    https://registry.npmjs.org/lottie-web/-/lottie-web-5.12.2.tgz /tmp/lottie-web.tgz
RUN install -d -m 0755 /opt/hq-media/lib /opt/hq-media/fonts \
    && tar -xzf /tmp/animejs.tgz -C /tmp package/lib/anime.min.js package/LICENSE.md \
    && install -m 0644 /tmp/package/lib/anime.min.js /opt/hq-media/lib/anime.min.js \
    && install -m 0644 /tmp/package/LICENSE.md /opt/hq-media/lib/anime.LICENSE.md \
    && rm -rf /tmp/package \
    && tar -xzf /tmp/lottie-web.tgz -C /tmp package/build/player/lottie_light.min.js package/LICENSE.md \
    && install -m 0644 /tmp/package/build/player/lottie_light.min.js /opt/hq-media/lib/lottie.min.js \
    && install -m 0644 /tmp/package/LICENSE.md /opt/hq-media/lib/lottie.LICENSE.md \
    && rm -rf /tmp/package /tmp/animejs.tgz /tmp/lottie-web.tgz \
    && printf '%s  %s\n' \
       b5ce1be3c3f530f192e0f2571d1942846096d66119cbada34bfdc912c4873f35 /opt/hq-media/lib/anime.min.js \
       23cd2c01be3d4da8bb664645d03afaff40879c62dc5f8dfe075ab3aa35c108f3 /opt/hq-media/lib/lottie.min.js \
       | sha256sum -c -

# IRANYekanX: the woff2 files the render page serves, and the TTFs as a system
# font (the only family a composition may name); its licence file beside them.
# hadolint ignore=DL3022
COPY --from=design fonts/static/IRANYekanX-Regular.woff2 fonts/static/IRANYekanX-Medium.woff2 \
     fonts/static/IRANYekanX-DemiBold.woff2 fonts/static/IRANYekanX-Bold.woff2 \
     fonts/FontLicense.txt /opt/hq-media/fonts/
# hadolint ignore=DL3022
COPY --from=design fonts/static/IRANYekanX-Regular.ttf fonts/static/IRANYekanX-Medium.ttf \
     fonts/static/IRANYekanX-DemiBold.ttf fonts/static/IRANYekanX-Bold.ttf \
     /usr/share/fonts/truetype/iranyekanx/
RUN chmod 0644 /opt/hq-media/fonts/* /usr/share/fonts/truetype/iranyekanx/* \
    && fc-cache -f >/dev/null \
    && fc-list | grep -q IRANYekanX

COPY hq-common/src /app/hq-common/src
COPY media-render/assets.lock.json /app/media-render/assets.lock.json
COPY media-render/src /app/media-render/src

USER 10001
WORKDIR /tmp
ENTRYPOINT ["python3", "-m", "hq_media_render"]
CMD ["probe"]
