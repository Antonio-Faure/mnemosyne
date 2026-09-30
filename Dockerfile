FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN pip install -e .

EXPOSE 8080

# Default: run the perpetual heartbeat. Override with `serve` for the API.
CMD ["mnemosyne", "run"]
