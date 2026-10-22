# The cloud-init templates' test bench (prompt 09 §4): Ubuntu 24.04 as on a
# new Hetzner server, plus what an offline run needs from outside: Docker's
# real signing key and the pinned Node build (its sha256 checked here, at
# build time). No systemd in a container: systemctl is a recording shim.
FROM ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openssh-server=1:9.6p1-3ubuntu13.20 openssh-client=1:9.6p1-3ubuntu13.20 \
        sudo=1.9.15p5-3ubuntu5.24.04.4 python3=3.12.3-0ubuntu2.1 curl=8.5.0-2ubuntu10.16 \
        gnupg=2.4.4-2ubuntu17.6 ca-certificates=20260816ubuntu0.24.04.1 \
        xz-utils=5.6.1+really5.4.5-1ubuntu0.4 git=1:2.43.0-1ubuntu7.4 iproute2=6.1.0-1ubuntu6.4 \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -m 0755 /fixtures \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /fixtures/docker.asc \
    && curl -fsSL https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-x64.tar.xz -o /fixtures/node.tar.xz \
    && echo "fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6  /fixtures/node.tar.xz" | sha256sum -c -

COPY shims /shims
COPY receiver.py check.py /bench/
# Login shells (runuser -l) find the shims first, like root does.
RUN chmod 0755 /shims/* \
    && printf 'export PATH="/shims:$PATH"\n' >/etc/profile.d/00-bench-shims.sh
