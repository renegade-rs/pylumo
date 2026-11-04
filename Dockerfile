# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
RUN groupadd --gid 10001 pylumo && \
    useradd --uid 10001 --gid 10001 --create-home --home-dir /home/pylumo pylumo \
    && mkdir -p /home/pylumo/.local/share \
    && chown pylumo:pylumo /home/pylumo/.local /home/pylumo/.local/share \
    && chmod 700 /home/pylumo/.local /home/pylumo/.local/share \
    && chmod 755 /home/pylumo
ENV PATH="/app/.venv/bin:${PATH}"
COPY --from=builder /app/.venv /app/.venv
WORKDIR /app
USER pylumo
EXPOSE 8443
ENTRYPOINT ["pylumo-serve"]
CMD ["--addr", "0.0.0.0:8443"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8443/', timeout=4); sys.exit(0 if r.status == 200 else 1)"
