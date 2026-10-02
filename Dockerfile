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

# mnemosyne house style: allow long edits. The harness default caps a compiled
# video at 32 s (maximumDurationBudget) and a 2-minute presentation is wanted.
RUN python - <<'PY'
import pathlib
p = pathlib.Path("/usr/local/lib/python3.12/site-packages/browser_harness/video.py")
t = p.read_text()
patch = t.replace('"maximumDurationBudget": 32', '"maximumDurationBudget": 180')
patch = patch.replace('"baseDurationBudget": 22', '"baseDurationBudget": 40')
assert '"maximumDurationBudget": 180' in patch, "browser_harness video.py changed"
p.write_text(patch)
PY

# browser-use disables vision by model-name heuristic: any model containing
# "deepseek" gets use_vision forced to False (PR #1399, written when DeepSeek
# was text-only). deepseek-v4.1-flash HAS native vision and there is no escape
# hatch — so the heuristic is disabled at build. The pinned browser-use version
# makes the patch predictable; if upstream changes, the no-op below prints it
# and the battery vision probe catches any regression (see docs/VISION-DEEPSEEK.md).
RUN python - <<'PY'
import pathlib
p = pathlib.Path(
    "/usr/local/lib/python3.12/site-packages/browser_use/agent/service.py"
)
t = p.read_text()
needle = "if 'deepseek' in self.llm.model.lower():"
if needle in t:
    p.write_text(t.replace(needle, "if False and 'deepseek' in self.llm.model.lower():"))
    print("vision patch: deepseek heuristic disabled")
else:
    print("vision patch: pattern not found (upstream changed) — no-op, check the probe")
PY

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 6080 9222 8080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["mnemosyne", "run"]
