# Thin desktop layer on top of the existing Playwright API image.
# Built by Cloud Build only — do not docker build this in Cloud Shell.
ARG API_IMAGE
FROM ${API_IMAGE}

USER root
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb x11vnc novnc websockify \
 && rm -rf /var/lib/apt/lists/*
