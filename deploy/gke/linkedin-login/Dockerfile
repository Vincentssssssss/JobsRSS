# Thin desktop layer on top of the existing Playwright API image.
# Built by Cloud Build only — do not docker build this in Cloud Shell.
ARG API_IMAGE
FROM ${API_IMAGE}

USER root
ENV DEBIAN_FRONTEND=noninteractive

# Debian novnc/websockify packages are what failed runtime apt-get in GKE.
# Install only Xvfb/x11vnc from apt; get websockify from pip and noVNC from GitHub.
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb x11vnc ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m pip install --no-cache-dir --retries 5 --timeout 120 \
      --index-url https://pypi.org/simple \
      --trusted-host pypi.org \
      --trusted-host files.pythonhosted.org \
      websockify \
 && mkdir -p /usr/share/novnc \
 && curl -fsSL https://github.com/novnc/noVNC/archive/refs/tags/v1.5.0.tar.gz \
    | tar -xz --strip-components=1 -C /usr/share/novnc \
 && test -f /usr/share/novnc/vnc.html
