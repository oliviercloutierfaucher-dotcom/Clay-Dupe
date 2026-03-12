#!/bin/bash
set -e

# Ensure data directory exists and is writable
mkdir -p /data
if [ ! -w /data ]; then
    echo "WARN: /data not writable, attempting chmod..." >&2
    chmod 777 /data 2>/dev/null || true
fi

# Start Streamlit (exec replaces shell for proper signal handling)
exec streamlit run ui/app.py \
    --server.port="${PORT:-8501}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
