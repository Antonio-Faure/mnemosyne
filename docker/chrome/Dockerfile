# Dedicated real-Chrome browser for the agent.
# Headful Chrome under Xvfb, exposed over CDP (9222) and VNC/noVNC for manual
# human intervention (initial Google login, hard captcha, phone verification).
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget gnupg gosu \
        xvfb x11-utils x11vnc novnc websockify \
        fonts-liberation fonts-noto \
        procps \
    && wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    # Chrome refuses to run its sandbox as root; run it as an unprivileged user
    # so we can keep the sandbox enabled (no more "--no-sandbox" warning).
    && groupadd -g 1000 chrome \
    && useradd -m -u 1000 -g 1000 -s /bin/bash chrome

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV DISPLAY=:99
EXPOSE 9222 5900 6080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
