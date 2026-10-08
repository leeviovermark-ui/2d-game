# Build from the repository root: docker build -f deploy/Dockerfile .
# Export the Godot Web client first; personal saves never enter this context.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 worldforge \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /app worldforge \
    && mkdir /data \
    && chown 10001:10001 /data

COPY --chown=10001:10001 server ./server
COPY --chown=10001:10001 shared/definitions.json ./shared/definitions.json
COPY --chown=10001:10001 assets/fonts/LICENSE.txt ./licenses/DejaVuSans.txt
COPY --chown=10001:10001 assets/licenses/Godot-4.6.3-notices.txt ./licenses/Godot-4.6.3-notices.txt
COPY --chown=10001:10001 build/web ./build/web
RUN test -s build/web/index.html \
    && test -s build/web/index.wasm \
    && test -s build/web/index.pck

USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=15s --timeout=4s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3); assert r.status == 200"
ENTRYPOINT ["python", "-m", "server.main"]
CMD ["--host", "0.0.0.0", "--public", "--database", "/data/worldforge.sqlite3"]
