# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy only the necessary files (no extra files)
COPY .env database.py outlook_auth.py email_service.py bot_main.py callback_server.py ./

# Create a non-root user to run the app
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Expose port for Flask callback server
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)"

# Run both bot and callback server using supervisor
CMD ["sh", "-c", "python callback_server.py & python bot_main.py"]
