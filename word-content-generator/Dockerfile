FROM python:3.12-slim

# Build context is the repo ROOT (bubble-word-tools/), so both the Word Content
# generator and the sibling Level Generator get bundled into one image/server.
WORKDIR /app
COPY word-content-generator/ /app/
COPY level-generator/ /app/level-generator/
RUN pip install --no-cache-dir -e ".[web]" \
    && cp -r data /app/data-seed \
    && chmod +x docker-entrypoint.sh

# The unified server serves the Level Generator tab from here.
ENV WCG_LEVELS_DIR=/app/level-generator

EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
