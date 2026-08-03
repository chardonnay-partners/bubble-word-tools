#!/bin/sh
# Seed the persistent /app/data volume from the repo copy on first boot,
# so picks made in the deployed instance survive redeploys.
set -e
if [ -z "$(ls -A /app/data 2>/dev/null)" ]; then
  cp -r /app/data-seed/. /app/data/
fi
exec wcg-serve
