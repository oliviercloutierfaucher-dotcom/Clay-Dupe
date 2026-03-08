FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install the package (makes clay-dupe CLI available)
RUN pip install --no-cache-dir -e .

# Create data directory for SQLite persistence
RUN mkdir -p /data

# Default DB path inside the persistent volume
ENV DB_PATH=/data/clay_dupe.db

# Run as non-root user for container security
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser
RUN chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8501

# Streamlit config: disable CORS/XSRF for local network use
CMD ["streamlit", "run", "ui/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--browser.gatherUsageStats=false"]
