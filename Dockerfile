FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DISPLAY=:99 \
    HOME=/home/agent \
    BU_CDP_URL=http://127.0.0.1:9222 \
    BH_HOME=/app/data/browser-harness \
    CHROME_PROFILE_DIR=/app/data/chrome-profile

# One container = app + real Chrome (Xvfb + VNC) + ffmpeg + git + browser-harness.
# Everything runs as the same uid (1000), so Chrome's sandbox is enabled and the
# agent, the browser and the recording share the same filesystem/paths.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget gnupg \
        xvfb x11-utils x11vnc novnc websockify ffmpeg git \
        fonts-liberation fonts-noto procps \
    && wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /home/agent && chown 1000:1000 /home/agent

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN pip install -e '.[browser]'

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 6080 9222 8080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["mnemosyne", "run"]
